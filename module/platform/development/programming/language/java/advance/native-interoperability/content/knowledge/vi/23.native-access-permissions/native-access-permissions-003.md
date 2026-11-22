# Phân biệt quyền truy cập native với `--enable-preview` và `--add-opens`

## Mục tiêu và bối cảnh

Java dùng nhiều cơ chế kiểm soát khác nhau khi ứng dụng tiến sát ranh giới của nền tảng: **restricted native operations** (JNI/Foreign Function & Memory API), **preview features** và **đóng gói module** (JPMS). Ba tùy chọn `--enable-native-access`, `--enable-preview`, `--add-opens` tương ứng với ba cơ chế này. Chúng có thể xuất hiện cùng nhau trong lệnh `java`, nhưng **không thay thế nhau**.

Hãy phân biệt ba câu hỏi:

1. **Native access:** Module nào được phép thực hiện thao tác native bị JDK đánh dấu là restricted?
2. **Preview:** Phiên bản JDK hiện tại có được phép sử dụng tính năng Java còn ở giai đoạn preview không?
3. **Deep reflection:** Module tiêu thụ nào được phản chiếu truy cập sâu vào package của module khác?

## 1. Bảng đối chiếu ba tùy chọn

| Cờ JVM | Mục đích thật sự | Phạm vi tác động | Không có tác dụng |
| --- | --- | --- | --- |
| `--enable-native-access=M1,M2` hoặc `--enable-native-access=ALL-UNNAMED` | Cho phép restricted native operations, gồm các thao tác FFM và từ JDK 24 là cả các thao tác JNI bị hạn chế | Các **module thực hiện** native operation; `ALL-UNNAMED` bao phủ mã trên class path | Không mở private fields qua reflection; không bật preview; không tự cài/nạp được một thư viện còn thiếu |
| `--enable-preview` | Cho phép sử dụng preview language/VM features của đúng release JDK | Compiler và runtime tương ứng với feature preview | Không cấp quyền native, không mở JPMS package |
| `--add-opens=sourceModule/package=targetModule` | Cho phép **deep reflection** vào package của source module từ target module | Một package và các module đích được chỉ định | Không làm restricted FFM/JNI operation hợp lệ; không bật preview |

Một package mở bằng `--add-opens` chỉ thay đổi quy tắc truy cập phản chiếu; nó không bảo đảm an toàn hoặc quyền gọi mã native. Ngược lại, native permission không cấp quyền đọc/ghi trường private của các class trong `java.base`.

### Native access: quyền theo module thực hiện thao tác

Tùy chọn có hai dạng thường gặp:

- `--enable-native-access=ALL-UNNAMED`: áp dụng cho **mọi unnamed module**, thường là ứng dụng và thư viện nằm trên class path.
- `--enable-native-access=com.example.nativebridge`: cấp quyền cụ thể cho named module `com.example.nativebridge`; có thể liệt kê nhiều tên module bằng dấu phẩy.

Ví dụ cấu hình cho ứng dụng chạy trên class path:

```bash
java --enable-native-access=ALL-UNNAMED -cp app.jar com.example.Main
```

Ví dụ cho ứng dụng module hóa, trong đó `com.example.nativebridge` chứa các thao tác restricted:

```bash
java --enable-native-access=com.example.nativebridge -p mods -m com.example.app/com.example.app.Main
```

Đây là **mẫu lệnh cấu hình**, tùy dự án cần có JAR, module path và main class tương ứng. Quyền được kiểm tra theo module chứa thao tác bị hạn chế, không đơn giản theo nơi đặt `main()`. Nếu thư viện JNI/FFM gọi thao tác restricted trong module riêng, chỉ cấp quyền cho module ứng dụng có thể vẫn thiếu.

Kể từ **JDK 24**, JEP 472 chuẩn hóa cách xử lý restricted operations của JNI và FFM. Trong đó có nạp thư viện bằng `System.load`/`System.loadLibrary`, khai báo phương thức `native` và các phương thức FFM như `Linker.downcallHandle`, `SymbolLookup.libraryLookup` hoặc `MemorySegment.reinterpret`. Cơ chế này bảo vệ tính toàn vẹn JVM trước các thao tác mà runtime không thể chứng minh là an toàn.

Trên **JDK 24–25**, chính sách `--illegal-native-access` quy định phản ứng khi thiếu quyền:

| Giá trị | Khi module chưa được cấp quyền native |
| --- | --- |
| `warn` (mặc định của JDK 24–25) | Cho chạy, in cảnh báo cho lần truy cập native bất hợp lệ đầu tiên của mỗi module |
| `deny` | Từ chối bằng `IllegalCallerException` |
| `allow` | Cho chạy, không cảnh báo; chỉ nên coi là cơ chế chuyển tiếp |

Một release tương lai dự kiến dùng `deny` làm mặc định; vì vậy khi kiểm thử migration nên chủ động chọn `--illegal-native-access=deny` và cấp native access cần thiết. Phiên bản JDK trước 24 có lịch sử chính sách khác, không suy ngược bảng trên cho mọi release.

### Preview: trạng thái của tính năng Java

Preview feature là tính năng ngôn ngữ/VM chưa được chốt thành chuẩn ổn định, được phát hành để lấy phản hồi. Nếu code dùng feature preview của JDK release `N`, phải bật `--enable-preview` tại **hai thời điểm**: biên dịch với `javac --enable-preview --release N` (hoặc `--source N`), và chạy với `java --enable-preview` trên đúng bản JDK tương ứng. Lớp dùng preview từ bản JDK cũ không được bảo đảm tương thích preview với JDK mới.

**Điểm dễ nhầm với FFM:** Foreign Function & Memory API trở thành API **chính thức trong JDK 22** (JEP 454), vì vậy dùng API FFM đã ổn định trên JDK 22+ không tự yêu cầu `--enable-preview`. Tuy nhiên một số phương thức FFM vẫn bị đánh dấu **restricted**, nên vẫn có thể cần `--enable-native-access`. Khi một chương trình vừa dùng một preview feature, vừa gọi restricted native operation, **cả hai quyền** đều cần được xử lý độc lập.

### Open package: quyền reflection

Ví dụ:

```bash
java --add-opens=java.base/java.lang=ALL-UNNAMED MyApp
```

Ý nghĩa: mở package `java.lang` của module `java.base` cho các unnamed modules truy cập sâu bằng reflection, như `Field.setAccessible(true)`. Tùy chọn này không bật quyền JNI/FFM. Ngoài ra, `--add-exports` phục vụ quyền truy cập các public types trong package qua ranh giới module; `--add-opens` phục vụ deep reflection. Hãy chỉ mở package cụ thể thật sự cần và ưu tiên thư viện dùng API public được hỗ trợ.

## 2. Thực hành: một chương trình kiểm tra cả hai loại quyền

Ví dụ **JDK 25** dưới đây chạy độc lập và không yêu cầu thư viện C. Nó chỉ **tạo** FFM downcall handle bằng một restricted method, không gọi hàm native nào; đồng thời thử reflection vào private field của `String`. Dùng thêm `--illegal-native-access=deny` để kết quả rõ ràng, tránh phụ thuộc cảnh báo `stderr` theo mặc định.

Tạo file **`AccessGates.java`**:

```java
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.reflect.Field;
import java.lang.reflect.InaccessibleObjectException;

public class AccessGates {
    public static void main(String[] args) throws NoSuchFieldException {
        Module caller = AccessGates.class.getModule();
        System.out.println("Native access: " + caller.isNativeAccessEnabled());

        try {
            Linker.nativeLinker().downcallHandle(FunctionDescriptor.ofVoid());
            System.out.println("Restricted FFM: ALLOWED");
        } catch (IllegalCallerException e) {
            System.out.println("Restricted FFM: DENIED");
        }

        Field valueField = String.class.getDeclaredField("value");
        try {
            valueField.setAccessible(true);
            System.out.println("Deep reflection: ALLOWED");
        } catch (InaccessibleObjectException e) {
            System.out.println("Deep reflection: DENIED");
        }
    }
}
```

Biên dịch bằng **JDK 25**:

```bash
javac --release 25 AccessGates.java
```

Chạy các kịch bản sau trên **JDK 25** (các tùy chọn đặt **trước** tên main class):

| Lệnh `java` | Dòng `Native access` | Dòng `Restricted FFM` | Dòng `Deep reflection` |
| --- | --- | --- | --- |
| `java --illegal-native-access=deny AccessGates` | `false` | `DENIED` | `DENIED` |
| `java --illegal-native-access=deny --enable-native-access=ALL-UNNAMED AccessGates` | `true` | `ALLOWED` | `DENIED` |
| `java --illegal-native-access=deny --add-opens=java.base/java.lang=ALL-UNNAMED AccessGates` | `false` | `DENIED` | `ALLOWED` |
| `java --illegal-native-access=deny --enable-preview AccessGates` | `false` | `DENIED` | `DENIED` |
| `java --illegal-native-access=deny --enable-native-access=ALL-UNNAMED --add-opens=java.base/java.lang=ALL-UNNAMED AccessGates` | `true` | `ALLOWED` | `ALLOWED` |

Ví dụ stdout **chính xác** khi bật native access nhưng không mở package reflection:

```text
Native access: true
Restricted FFM: ALLOWED
Deep reflection: DENIED
```

Stdout **chính xác** khi chỉ mở package reflection:

```text
Native access: false
Restricted FFM: DENIED
Deep reflection: ALLOWED
```

Giải thích: `Module.isNativeAccessEnabled()` phản ánh native permission của module đang chạy. `Linker.downcallHandle(...)` là restricted method, nên dưới chính sách `deny` chỉ thành công khi module được cấp native access. `String.value` là private field nằm trong package `java.lang` của `java.base`; `setAccessible(true)` chỉ được cho phép khi package đó đã mở cho unnamed module của chương trình. `--enable-preview` không làm thay đổi bài thử này vì code không dùng preview feature.

Nếu **không** chỉ định `--illegal-native-access=deny` trên JDK 25, FFM thiếu quyền có thể vẫn trả về handle nhưng sinh **cảnh báo ở stderr**. Điều đó không có nghĩa module đã được cấp native access. Cũng không nên dùng `--enable-preview` để thử “tắt cảnh báo native”.

## 3. Bảng chẩn đoán khi chạy ứng dụng thực tế

| Triệu chứng | Cách xác định và sửa đúng |
| --- | --- |
| Cảnh báo “restricted native access” khi nạp JNI library hoặc gọi FFM trên JDK 24+ | Tìm module chứa thao tác bị hạn chế; cấp `--enable-native-access` cho module đó, sau đó thử `--illegal-native-access=deny`. |
| `IllegalCallerException` từ phương thức FFM restricted với `deny` | Module gọi phương thức thiếu native permission; mở package bằng `--add-opens` không giải quyết. |
| `InaccessibleObjectException` từ `setAccessible(true)` | Kiểm tra reflective access tới module/package nào; ưu tiên cập nhật thư viện, hoặc thêm `--add-opens=sourceModule/package=consumer` đúng phạm vi. |
| `javac` hoặc JVM báo preview features disabled | Code thực sự dùng preview; bật `--enable-preview` tại compile và runtime, cùng phiên bản release. |
| `UnsatisfiedLinkError` lúc nạp thư viện native | Kiểm tra file native, tên, vị trí tìm kiếm, kiến trúc/ABI, phụ thuộc của thư viện. Native permission không tự cung cấp file `.dll`, `.so` hoặc `.dylib`. |

Một ứng dụng có thể cần **cả ba cờ** nếu ba cơ chế cùng được sử dụng, nhưng từng cờ phải có lý do cụ thể. Ví dụ: một thư viện thao tác JNI, một framework phản chiếu vào nội bộ JDK, và code của chính ứng dụng dùng cú pháp preview là ba tình huống riêng.

## 4. Lỗi thường gặp và nguyên tắc cấu hình

- **“FFM là API final nên không còn giới hạn native.”** Sai: API có thể ổn định nhưng các thao tác ảnh hưởng tính toàn vẹn JVM vẫn restricted.
- **“`--enable-preview` cho phép chạy mã C.”** Sai: preview cho phép tính năng Java đang thử nghiệm, không phải quyền vượt ranh giới native.
- **“`--add-opens` giống `--enable-native-access`.”** Sai: một bên là deep reflection trong hệ module, một bên là quyền restricted native operation.
- **“Không có exception nghĩa là native permission đã đúng.”** Trên JDK 24–25, `warn` cho phép chạy kèm cảnh báo; thử `deny` để đánh giá readiness.
- **“Luôn cấp native access cho module của `main()`.”** Không đúng khi thư viện ở module khác mới là nơi chứa restricted operation.
- **“`ALL-UNNAMED` chỉ cấp cho class hiện tại.”** Sai: nó áp dụng cho mọi unnamed module, thường bao gồm toàn bộ class path.
- **“Cứ thêm nhiều `--add-opens` cho hết lỗi.”** Điều đó mở thêm reflective access, gây cấu hình khó kiểm toán; nên sửa phụ thuộc và chỉ mở đúng package cần thiết.

Quy trình xử lý nên là: kiểm tra `java -version` → xác định loại lỗi và phiên bản API → xác định module/package đích → chọn đúng cờ với phạm vi nhỏ nhất → chạy kiểm thử dưới `--illegal-native-access=deny` (JDK 24+) và xác minh binary native hoạt động trên môi trường triển khai. Công cụ `jnativescan` trên JDK mới có thể giúp tìm dấu vết sử dụng JNI và restricted methods; `Module.isNativeAccessEnabled()` giúp xác thực native permission từ Java code.

**Ghi nhớ:** `--enable-native-access` quản lý **quyền thao tác native**, `--enable-preview` quản lý **tính năng Java chưa chốt**, và `--add-opens` quản lý **deep reflection qua package/module**.

## Tham khảo chính thức

- [Oracle JDK 25 — Java launcher options](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)
- [Oracle JDK 25 — Restricted methods](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/doc-files/RestrictedMethods.html)
- [Oracle JDK 25 — Restricted method list](https://docs.oracle.com/en/java/javase/25/docs/api/restricted-list.html)
- [Oracle JDK 25 — Preview language/VM features](https://docs.oracle.com/en/java/javase/25/language/preview-language-vm-features.html)
- [Oracle JDK 25 — Migrating from older JDKs](https://docs.oracle.com/en/java/javase/25/migrate/migrating-jdk-8-later-jdk-releases.html)
- [Inside Java — JDK 24 restricted native access update](https://inside.java/2024/12/09/quality-heads-up/)