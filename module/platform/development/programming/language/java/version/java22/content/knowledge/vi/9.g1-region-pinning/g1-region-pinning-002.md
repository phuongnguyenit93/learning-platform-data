# JNI critical region qua `GetPrimitiveArrayCritical` và `GetStringCritical`

JNI cho phép mã native truy cập dữ liệu của primitive array và `String` trong Java heap thông qua hai cặp hàm `GetPrimitiveArrayCritical` / `ReleasePrimitiveArrayCritical` và `GetStringCritical` / `ReleaseStringCritical`. Các hàm này có thể giúp tránh một lần sao chép dữ liệu lớn, nhưng đổi lại tạo ra một *critical region* với những giới hạn nghiêm ngặt: phải giữ vùng này thật ngắn, không gọi các JNI function tùy ý và không thực hiện thao tác có thể block.

Trong JDK 22, G1 được cải tiến qua JEP 423 để có thể tiếp tục garbage collection trong khi JNI critical region đang hoạt động bằng cơ chế region pinning. Cần phân biệt hai lớp kiến thức: các hàm JNI critical đã tồn tại từ JDK 1.2 và vẫn có trong JNI Specification hiện hành; thay đổi của JDK 22 là cách G1 xử lý đối tượng đang được native code giữ con trỏ. Region pinning là chi tiết triển khai của G1, không làm mất các giới hạn trong hợp đồng JNI.

## 1. JNI critical region là gì?

Một Java object thường được garbage collector di chuyển khi thu gom và compact heap. Nếu native code giữ một con trỏ thô tới phần tử của Java array hoặc nội dung `String`, con trỏ đó có thể mất hiệu lực nếu object bị di chuyển.

JNI cung cấp các cặp hàm lấy và trả con trỏ:

```text
Java heap object
      |
      | GetPrimitiveArrayCritical / GetStringCritical
      v
Native pointer
      |
      | native code đọc hoặc xử lý dữ liệu trong thời gian ngắn
      v
ReleasePrimitiveArrayCritical / ReleaseStringCritical
      |
      v
VM được thông báo rằng native code không còn giữ pointer
```

Khoảng thời gian từ hàm `Get...Critical` tới hàm `Release...Critical` tương ứng được gọi là critical region hoặc critical section. VM có thể trả về địa chỉ trực tiếp của dữ liệu nếu có thể, hoặc tạo một bản sao rồi trả con trỏ tới bản sao đó. Vì vậy, chương trình không được giả định rằng pointer luôn trỏ trực tiếp vào vùng nhớ gốc của Java object.

Critical region được thiết kế cho một đoạn native code ngắn, chủ yếu là đọc hoặc xử lý dữ liệu trong bộ nhớ. Nó không phải cơ chế để giữ con trỏ qua nhiều lời gọi native, lưu pointer vào biến toàn cục, thực hiện I/O hoặc chạy một tác vụ dài.

## 2. Hai cặp hàm JNI cần biết

### 2.1. Primitive array

Các chữ ký JNI:

```c
void * GetPrimitiveArrayCritical(
        JNIEnv *env,
        jarray array,
        jboolean *isCopy);

void ReleasePrimitiveArrayCritical(
        JNIEnv *env,
        jarray array,
        void *carray,
        jint mode);
```

`GetPrimitiveArrayCritical` nhận một Java primitive array như `jintArray`, `jbyteArray` hoặc `jdoubleArray`. Hàm trả về pointer tới phần tử của array, hoặc `NULL` nếu không thể lấy pointer. Tham số `isCopy` có thể là `NULL`; nếu được truyền vào, VM đặt nó thành `JNI_TRUE` khi trả về bản sao và `JNI_FALSE` khi không sao chép.

Pointer chỉ hợp lệ cho tới khi gọi `ReleasePrimitiveArrayCritical` tương ứng. Khi release, phải truyền đúng array và pointer đã nhận từ lần acquire đó.

### 2.2. Java String

Các chữ ký JNI:

```c
const jchar * GetStringCritical(
        JNIEnv *env,
        jstring string,
        jboolean *isCopy);

void ReleaseStringCritical(
        JNIEnv *env,
        jstring string,
        const jchar *carray);
```

`GetStringCritical` trả về pointer chỉ đọc tới các `jchar` của Java `String`. `jchar` là một code unit UTF-16 rộng 16 bit. Nếu ký tự nằm ngoài Basic Multilingual Plane, nó được biểu diễn bằng một cặp surrogate, do đó số `jchar` không đồng nghĩa với số Unicode code point.

Hàm không trả về chuỗi UTF-8 hoặc modified UTF-8. Native code phải dùng độ dài lấy bằng `GetStringLength` và xử lý đúng các code unit UTF-16. Hãy lấy độ dài trước khi vào critical region; không gọi `GetStringLength` trong khoảng thời gian đang giữ pointer critical.

Khác với pointer của primitive array, pointer từ `GetStringCritical` là `const jchar *`: không được sửa nội dung chuỗi qua pointer này. Java `String` cũng là immutable.

## 3. Vì sao phải giới hạn critical region?

JNI Specification yêu cầu native code không chạy quá lâu giữa hàm acquire và release. Trong critical region:

- Không gọi các JNI function tùy ý. Chỉ gọi hàm release tương ứng để kết thúc vùng critical.
- Không gọi system call hoặc API có thể block và chờ một Java thread khác.
- Không chờ I/O, network, lock, condition variable, semaphore hoặc tác vụ khác.
- Không gọi callback vào Java, không tạo Java object và không thực hiện công việc có thể kích hoạt xử lý runtime.
- Không giữ pointer sau khi đã gọi release.

Ví dụ nguy hiểm là lấy pointer bằng `GetPrimitiveArrayCritical`, sau đó chờ đọc dữ liệu từ pipe mà một Java thread khác mới có thể ghi. Nếu thread Java cần GC hoặc cần tiến triển để hoàn thành thao tác, native thread có thể khiến hệ thống bị đình trệ hoặc deadlock.

Trong critical region, chỉ nên thực hiện thao tác bộ nhớ ngắn và có thời gian thực thi dự đoán được, chẳng hạn vòng lặp tính tổng, so sánh, sao chép hoặc biến đổi dữ liệu đơn giản. Nếu thuật toán cần gọi thư viện có thể block, cấp phát phức tạp hoặc xử lý trong thời gian dài, hãy dùng API truy cập array/string khác.

## 4. Ví dụ đọc primitive array trong critical region

Ví dụ sau tính tổng một `int[]` trong native code. Độ dài array được lấy trước khi vào critical region; sau khi lấy pointer, native code chỉ duyệt dữ liệu rồi release ngay.

```c
#include <jni.h>

static jlong sum_int_array(JNIEnv *env, jintArray array) {
    /* array must be non-NULL, as required by this helper's contract. */
    jsize length = (*env)->GetArrayLength(env, array);

    jint *elements = (jint *) (*env)->GetPrimitiveArrayCritical(
            env, array, NULL);
    if (elements == NULL) {
        /* A VM exception may already be pending, for example OOME. */
        return 0;
    }

    jlong sum = 0;
    for (jsize i = 0; i < length; i++) {
        sum += elements[i];
    }

    (*env)->ReleasePrimitiveArrayCritical(
            env, array, elements, JNI_ABORT);
    return sum;
}
```

`GetArrayLength` được gọi trước `GetPrimitiveArrayCritical`, bởi đây là JNI function khác và không nên gọi bên trong critical region. Nếu acquire trả về `NULL`, không có pointer để release; ví dụ trả về ngay trong khi VM có thể đã đặt một exception pending.

Ví dụ chỉ đọc array nên truyền `JNI_ABORT`. Khi pointer là bản sao, mode này yêu cầu VM bỏ bản sao mà không copy dữ liệu về array gốc. Nếu VM đã pin và trả pointer trực tiếp, mode không thể hoàn tác thay đổi đã ghi vào vùng nhớ gốc. Do ví dụ không ghi dữ liệu nên không có khác biệt về kết quả.

## 5. Release mode của primitive array

`ReleasePrimitiveArrayCritical` nhận `mode` giống họ hàm `Release<PrimitiveType>ArrayElements`:

| Mode | Nếu VM trả về bản sao | Nếu VM trả pointer trực tiếp |
| --- | --- | --- |
| `0` | Copy nội dung về array gốc rồi giải phóng bản sao. | Bỏ pin và kết thúc quyền truy cập. |
| `JNI_COMMIT` | Copy nội dung về array gốc nhưng vẫn giữ bản sao; cần một lần release cuối để giải phóng. | Mode bị bỏ qua; pointer vẫn là dữ liệu gốc. |
| `JNI_ABORT` | Giải phóng bản sao mà không copy thay đổi về array gốc. | Mode bị bỏ qua; các thay đổi đã ghi trực tiếp vẫn tồn tại. |

Trong phần lớn trường hợp, `0` là lựa chọn dễ hiểu nhất nếu native code có sửa array và muốn ghi kết quả về Java. `JNI_ABORT` phù hợp khi chỉ đọc hoặc không muốn copy dữ liệu của một bản sao về array. Đừng dùng `JNI_ABORT` như một thao tác rollback: nếu VM đã trả pointer trực tiếp và native code sửa dữ liệu, thay đổi đã xảy ra trên array gốc.

`JNI_COMMIT` không phải release cuối cùng khi VM đã tạo bản sao. Sau khi commit, native code vẫn phải gọi `ReleasePrimitiveArrayCritical` thêm lần nữa với `0` hoặc `JNI_ABORT` để kết thúc quyền truy cập và giải phóng buffer.

## 6. Ví dụ đọc Java String trong critical region

Ví dụ sau tính tổng các code unit UTF-16 của một chuỗi. Độ dài được đọc trước khi acquire; pointer được dùng đúng số phần tử và release ngay sau vòng lặp.

```c
#include <jni.h>

static jlong sum_string_code_units(JNIEnv *env, jstring text) {
    /* text must be non-NULL, as required by this helper's contract. */
    jsize length = (*env)->GetStringLength(env, text);

    const jchar *characters = (*env)->GetStringCritical(
            env, text, NULL);
    if (characters == NULL) {
        /* A VM exception may already be pending. */
        return 0;
    }

    jlong sum = 0;
    for (jsize i = 0; i < length; i++) {
        sum += characters[i];
    }

    (*env)->ReleaseStringCritical(env, text, characters);
    return sum;
}
```

Không dùng `strlen()` hoặc tìm byte NUL trên pointer này. `GetStringCritical` trả về dãy `jchar` có độ dài xác định, không phải C string. Duyệt theo `GetStringLength` cũng tránh đọc ngoài phạm vi chuỗi.

`GetStringCritical` không có tham số release mode. Luôn gọi `ReleaseStringCritical` với đúng `jstring` và pointer nhận được. Không được thay bằng `ReleaseStringChars` hoặc `ReleaseStringUTFChars`; mỗi hàm release phải khớp với hàm acquire tương ứng.

## 7. Region pinning của G1 từ JDK 22

Trước JDK 22, một collector có thể phải trì hoãn hoặc tạm vô hiệu hóa một số hoạt động garbage collection trong khi native code giữ pointer critical, tùy cách triển khai của VM. Điều này có thể làm critical region kéo dài gây ảnh hưởng tới độ trễ GC.

JEP 423 đưa *Region Pinning for G1* vào JDK 22. Với G1, VM có thể giữ các object được native code tham chiếu ở vị trí an toàn trong critical region và vẫn thu gom các vùng heap khác. G1 không cần vô hiệu hóa toàn bộ garbage collection chỉ vì một JNI critical region đang hoạt động.

Ý nghĩa thực tế:

- GC vẫn có thể chạy và xử lý những region không bị pin.
- Object đang được native code sử dụng không được di chuyển trong khoảng thời gian cần bảo vệ pointer.
- Region có object pinned có thể không được evacuate trong một GC pause; G1 có thể thử thu gom region đó ở các chu kỳ tiếp theo.
- Log GC có thể ghi `Evacuation Failure: Pinned` khi G1 không thể di chuyển object đang pinned.

Region pinning không biến critical region thành vùng có thể giữ lâu. Object pinned vẫn hạn chế khả năng evacuate region, có thể làm giảm hiệu quả thu hồi bộ nhớ trong một pause và tạo thêm công việc cho các GC sau. Vì vậy, nguyên tắc giữ critical region thật ngắn vẫn quan trọng.

### Giới hạn về collector và implementation

JEP 423 là cải tiến của G1 trong HotSpot. Đây không phải một API Java để ứng dụng tự pin/unpin object và cũng không thay đổi contract của JNI. Không được suy luận rằng mọi collector, mọi JVM vendor hoặc mọi runtime đều xử lý critical region giống G1. JNI Specification vẫn cho phép VM trả pointer trực tiếp hoặc bản sao và vẫn yêu cầu native code tuân thủ các giới hạn critical region.

## 8. Theo dõi pinning và chẩn đoán JNI

Khi điều tra độ trễ GC hoặc vấn đề JNI, có thể dùng GC logging:

```bash
java -Xlog:gc -jar app.jar
```

Với G1, log có thể chứa `Evacuation Failure: Pinned`. Đây là dấu hiệu G1 gặp object không thể di chuyển trong lần evacuation đó; nó có thể liên quan tới một pointer được giữ bằng `GetPrimitiveArrayCritical` hoặc JNI call tương tự. Không nên chỉ dựa vào một dòng log để kết luận toàn bộ nguyên nhân hiệu năng; hãy xem thêm thời gian pause, tần suất GC, heap occupancy và thời gian native giữ pointer.

`-Xcheck:jni` giúp phát hiện một số cách sử dụng JNI đáng ngờ, trong đó có lời gọi JNI khác trong phạm vi critical region:

```bash
java -Xcheck:jni -jar app.jar
```

Trên HotSpot JDK 27, một số lỗi JNI nghiêm trọng được `-Xcheck:jni` phát hiện có thể làm JVM kết thúc với lỗi không thể phục hồi, trong đó có lời gọi JNI khác trong critical region. Tùy chọn này làm giảm hiệu năng, vì vậy chủ yếu dùng khi kiểm thử và chẩn đoán. Nó không thay thế việc rà soát code native. Hãy kiểm tra mọi đường thoát sau acquire, bảo đảm pointer được release đúng một lần và không có nhánh lỗi nào giữ pointer quá thời hạn.

## 9. Khi nào nên dùng API khác?

Critical API phù hợp khi native code cần truy cập dữ liệu lớn, thao tác ngắn, không block và có thể hoàn tất ngay trong một đoạn code nhỏ. Nếu không đáp ứng điều kiện đó, hãy cân nhắc các lựa chọn sau:

| Nhu cầu | API nên xem xét | Đặc điểm |
| --- | --- | --- |
| Chỉ cần một đoạn nhỏ của primitive array | `Get<PrimitiveType>ArrayRegion` / `Set<PrimitiveType>ArrayRegion` | Sao chép một vùng dữ liệu vào/ra buffer native; không giữ critical pointer. |
| Cần pointer array nhưng thao tác không thể thỏa các giới hạn critical | `Get<PrimitiveType>ArrayElements` / `Release<PrimitiveType>ArrayElements` | VM có thể pin hoặc tạo bản sao; vẫn phải release đúng cách. |
| Cần đọc Java String với thời gian xử lý dài hơn | `GetStringChars` / `ReleaseStringChars` hoặc `GetStringUTFChars` / `ReleaseStringUTFChars` | Có thể trả bản sao; không có các hạn chế đặc biệt của critical region. |
| Cần sao chép nội dung String vào buffer tự quản lý | `GetStringRegion` hoặc `GetStringUTFRegion` | Copy theo vùng; không giữ pointer tới Java String. |
| Xây dựng tích hợp native mới từ Java hiện đại | Foreign Function & Memory API | API chính thức từ JDK 22; cho phép gọi native function và quản lý foreign memory mà không cần JNI cho nhiều trường hợp. |

Lưu ý `GetStringUTFChars` sử dụng **modified UTF-8** theo JNI, không phải lúc nào cũng tương đương UTF-8 tiêu chuẩn. Nếu native library yêu cầu UTF-8 chuẩn, cần chuyển mã rõ ràng hoặc dùng một giao thức byte/length phù hợp.

## 10. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Quên gọi hàm release | VM tiếp tục xem dữ liệu đang được native code giữ; pin/copy không được kết thúc đúng cách. | Bảo đảm mọi nhánh sau acquire đều release. |
| Gọi JNI function khác trong critical region | Vi phạm giới hạn JNI, có nguy cơ deadlock hoặc ảnh hưởng GC. | Chuẩn bị dữ liệu trước acquire; chỉ xử lý pointer rồi release. |
| Chờ I/O hoặc lock | Critical region kéo dài và có thể chờ một Java thread cần tiến triển. | Không block; chuyển I/O ra ngoài critical region. |
| Giữ pointer sau release | Pointer không còn hợp lệ; truy cập có thể gây memory corruption. | Không lưu pointer vào global state hoặc dùng sau release. |
| Không kiểm tra `NULL` từ hàm acquire | Có thể dereference pointer không hợp lệ sau lỗi cấp phát. | Kiểm tra pointer trước khi đọc/ghi. |
| Dùng `JNI_ABORT` để hoàn tác ghi trực tiếp | Nếu VM đã pin object, thay đổi đã được ghi vào array gốc. | Chỉ dựa vào `JNI_ABORT` để bỏ bản sao; không dùng như rollback. |
| Dùng `strlen()` trên `GetStringCritical` | Đọc sai kiểu dữ liệu và có thể vượt phạm vi chuỗi. | Dùng `GetStringLength` lấy trước và duyệt theo số `jchar`. |
| Cho rằng G1 pinning cho phép giữ pointer lâu | GC vẫn bị ảnh hưởng bởi region/object pinned và có thể phát sinh evacuation failure. | Giữ critical region ngắn bất kể collector. |

## 11. Quy trình sử dụng an toàn

Khi thật sự cần dùng JNI critical API, hãy theo thứ tự:

1. **Kiểm tra đầu vào** trước khi acquire; không truyền array hoặc string null.
2. **Lấy metadata cần thiết** như độ dài array/string trước critical region.
3. **Acquire pointer** bằng đúng hàm `Get...Critical`; kiểm tra `NULL` ngay.
4. **Xử lý thật ngắn** trong native code; không gọi JNI function khác, không block, không I/O và không gọi ngược vào Java.
5. **Release ngay** bằng đúng hàm release và đúng object/pointer tương ứng.
6. **Chỉ sử dụng kết quả sau release**; tuyệt đối không giữ hoặc truy cập pointer cũ.
7. **Đo kiểm trên collector mục tiêu**; không giả định hành vi pinning của G1 áp dụng cho mọi JVM.

## 12. Trạng thái API trên JDK hiện hành

Tại ngày 25-11-2026, JDK 27 là feature release mới nhất và JDK 25 là LTS mới nhất. JNI Specification của Java SE 27 vẫn liệt kê `GetPrimitiveArrayCritical`, `ReleasePrimitiveArrayCritical`, `GetStringCritical` và `ReleaseStringCritical`; tài liệu ghi nhận các hàm này có từ JDK/JRE 1.2. Chúng không phải preview API hay incubator API và vẫn thuộc JNI hiện hành, dù chỉ nên dùng khi thật sự cần quyền truy cập critical và có thể đáp ứng các giới hạn đi kèm.

Tính năng mới của Java 22 trong chủ đề này là JEP 423: G1 Region Pinning. JEP 423 thay đổi cách G1 xử lý object được native code giữ trong JNI critical region; nó không giới thiệu hai hàm JNI mới và không nới lỏng các quy tắc sử dụng JNI.

## 13. Kiến thức cần nhớ

- `GetPrimitiveArrayCritical` và `GetStringCritical` cung cấp pointer có thời hạn; phải gọi đúng hàm release tương ứng.
- VM có thể trả pointer trực tiếp hoặc bản sao; luôn kiểm tra kết quả acquire và không dựa vào `isCopy` để thay đổi logic.
- Critical region phải ngắn; không gọi JNI function tùy ý, không I/O, không chờ lock và không block.
- `GetStringCritical` trả `const jchar *` chứa UTF-16 code unit, không phải C string hoặc UTF-8.
- Release mode `JNI_ABORT` không thể hoàn tác thay đổi nếu VM đã trả pointer trực tiếp.
- JDK 22 JEP 423 giúp G1 tiếp tục GC bằng region pinning; object pinned vẫn có thể làm region không evacuate được trong một pause.
- Region pinning là chi tiết triển khai G1, không phải bảo đảm chung cho mọi collector/JVM.
- Các JNI critical API vẫn tồn tại trong JNI Specification Java SE 27; không phải API preview hoặc deprecated.
- Với thao tác dài hoặc cần block, ưu tiên region-copy APIs, `Get/Release...Elements`, string accessors hoặc FFM API tùy hợp đồng native.

## Tài liệu tham khảo

- [JEP 423: Region Pinning for G1](https://openjdk.org/jeps/423) — thay đổi G1 trong JDK 22 để tiếp tục garbage collection trong JNI critical regions.
- [Java Native Interface Specification — GetPrimitiveArrayCritical và ReleasePrimitiveArrayCritical (Java SE 27)](https://docs.oracle.com/en/java/javase/27/docs/specs/jni/functions.html#GetPrimitiveArrayCritical,-ReleasePrimitiveArrayCritical) — chữ ký, pointer, giới hạn critical region và release mode.
- [Java Native Interface Specification — GetStringCritical và ReleaseStringCritical (Java SE 27)](https://docs.oracle.com/en/java/javase/27/docs/specs/jni/functions.html#GetStringCritical,-ReleaseStringCritical) — truy cập UTF-16 string và các giới hạn critical.
- [JNI Design Overview — Accessing Primitive Arrays (Java SE 27)](https://docs.oracle.com/en/java/javase/27/docs/specs/jni/design.html#accessing-primitive-arrays) — lý do pinning/copy và các lựa chọn truy cập array.
- [Garbage-First (G1) Garbage Collector — Java SE 27](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-g1-garbage-collector.html) — pinned object, evacuation failure và cách G1 xử lý region không thể di chuyển.
- [The `java` Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html#extra-options-for-java) — hành vi và giới hạn chẩn đoán của `-Xcheck:jni`.
- [JEP 454: Foreign Function & Memory API](https://openjdk.org/jeps/454) — lựa chọn API chuẩn cho tích hợp native mới từ JDK 22.
- [Java Downloads — Oracle](https://www.oracle.com/java/technologies/downloads/) — xác nhận JDK 27 là release mới nhất và JDK 25 là LTS mới nhất tại thời điểm cập nhật bài.
