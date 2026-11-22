# Phương thức `<clinit>`, static field initializer và static block

> **Ngữ cảnh:** Java Core → ClassLoader → Khởi tạo lớp. Bài học tập trung vào mã chạy trong **giai đoạn khởi tạo class/interface** (class initialization), thứ tự thực thi các khai báo `static` và cách trình biên dịch biểu diễn chúng bằng phương thức JVM `<clinit>`. Các ví dụ hoàn chỉnh dưới đây dùng Java 17+, chạy độc lập theo đúng tên tệp.

## 1. Phải phân biệt ba khái niệm trước khi đọc mã

- **Static field initializer** là biểu thức gán ban đầu gắn với khai báo biến lớp, chẳng hạn `static int count = initialize();`. Biểu thức có thể có side effect, ném lỗi hoặc đọc field khác.
- **Static initializer block** là khối `static { ... }` trong thân `class`. Khối chứa các statement cần chạy trong quá trình khởi tạo lớp. Một lớp có thể có nhiều khối `static`, xen giữa các field initializer.
- **`<clinit>` (class/interface initialization method)** là phương thức đặc biệt ở **mức class file/JVM**, thường do compiler tạo để kết hợp các lệnh khởi tạo tĩnh cần thực thi. Nó không phải phương thức mà bạn tự khai báo, gọi trực tiếp hay override trong mã Java.

Sơ đồ tư duy:

~~~text
Mã nguồn Java                  Class file                    JVM runtime
static int a = compute(); ─┐
static { audit(a); } ───────┼──> <clinit>:()V ─────────────> chạy khi class được initialize
static int b = more(); ────┘       theo thứ tự nguồn

static final int SIZE = 64  ────> ConstantValue = 64 ─────> gán trước lúc chạy <clinit>
                                            (nếu compiler phát ra thuộc tính)
~~~

**Chú ý:** `static` thuộc về lớp nhưng **không đồng nghĩa** “chạy ngay lúc chương trình bắt đầu”. Lớp có thể đã được **load / verify / prepare** mà phần khởi tạo tĩnh vẫn chưa chạy. Một class không có công việc khởi tạo tĩnh cần thực thi có thể **không có `<clinit>`** trong bytecode.

## 2. Phân biệt nhanh với constructor `<init>`

`<clinit>:()V` là phương thức JVM dành cho mã khởi tạo static của class hoặc interface; class file có thể không có phương thức này nếu không có công việc static cần thực thi. `<init>(...)V` là constructor, có thể có nhiều overload và chạy cho từng instance. Java source không gọi trực tiếp `<clinit>`, còn JVM tự điều phối nó khi class được initialized. Với `new Demo()` lần đầu, initialization của class hoàn tất trước constructor; lần `new` tiếp theo vẫn gọi constructor nhưng không chạy lại initializer tĩnh.

Bài **Phân biệt `<clinit>` với constructor `<init>`** có ví dụ chạy nhiều lần `new` và giải thích instance field initializer, instance block, `super(...)`. Phần còn lại của bài này tập trung vào bytecode, thứ tự và giới hạn của **static initialization**.

## 3. Trước `<clinit>`, JVM đã làm gì?

Các giai đoạn quy định bởi JVM Specification:

~~~text
Loading                 Linking                                      Initialization
đọc / định nghĩa class  ├─ Verification: kiểm tra bytecode           ├─ gán ConstantValue nếu có
                        ├─ Preparation: tạo static fields, mặc định └─ chạy <clinit> nếu class có
                        └─ Resolution: giải symbolic references
                            (thời điểm có thể sớm hoặc lười)
~~~

Trong **preparation**, các trường static được tạo và có **giá trị mặc định**: `int` là `0`, `boolean` là `false`, reference là `null`. Đừng nói `static int x = 10` đã chạy “trong preparation”: biểu thức gán do mã nguồn tạo thuộc initialization.

Một điểm dễ nhầm: trường constant có `ConstantValue`. Theo JVMS, giá trị từ thuộc tính đó được gán **trong initialization, trước khi gọi `<clinit>`**; không phải JVM chạy một dòng bytecode Java thông thường cho hằng đó ngay tại vị trí khai báo. Vì vậy thuật toán JLS ưu tiên gán các **constant variables** trước những initializer khác.

Xem hai trường hợp:

~~~java
static final int PORT = 8080;                 // constant variable: int + constant expression
static final int RUNTIME_PORT = readPort();   // final, nhưng KHÔNG phải constant variable
~~~

`PORT` có thể được biểu diễn bằng `ConstantValue` và tham chiếu trực tiếp từ class khác có thể được compiler **inline**. `RUNTIME_PORT` đòi chạy biểu thức `readPort()` trong initialization, dù có `final`.

**Không có bảo đảm mọi symbolic reference được resolve cùng một thời điểm.** JVM có thể link/resolve sớm hoặc muộn theo giới hạn đặc tả; điều kiện kích hoạt initialization mới là thứ cần dựa vào, không phải việc log báo class vừa được load.

## 4. Static field initializer và static block được chạy theo thứ tự nào?

Với phần mã khởi tạo tĩnh bình thường, Java thực thi **field initializers và static blocks theo thứ tự chúng xuất hiện trong thân class**, sau các bước bắt buộc như gán compile-time constants và khởi tạo lớp cha cần thiết. Mỗi initializer có thể đọc trạng thái đã gán trước đó; một field khai báo sau nhưng chưa được gán vẫn có giá trị **mặc định**.

Ví dụ chạy được, tệp **`InitOrder.java`**:

~~~java
public class InitOrder {
    static class Demo {
        static int first = mark("field first", 10);

        static {
            System.out.println(
                "block: first=" + first + ", second=" + readSecond());
        }

        static int second = mark("field second", 20);

        static int readSecond() {
            return second;
        }

        static int mark(String name, int value) {
            System.out.println(name);
            return value;
        }
    }

    public static void main(String[] args) {
        System.out.println("before");
        System.out.println("result=" + Demo.second);
        System.out.println("again=" + Demo.first);
    }
}
~~~

~~~bash
javac --release 17 InitOrder.java
java InitOrder
~~~

Output thực tế trên OpenJDK 21 khi biên dịch với `--release 17`:

~~~text
before
field first
block: first=10, second=0
field second
result=20
again=10
~~~

Diễn giải từng bước:

1. JVM bắt đầu initialize `Demo` khi cần đọc `Demo.second`, là trường static **không phải constant variable**.
2. Ban đầu `first=0` và `second=0` do preparation.
3. `first = mark(...)` in `field first`, rồi đặt `first=10`.
4. Khối `static` chạy; `readSecond()` thấy `second=0` vì initializer của `second` nằm **sau** khối này.
5. `second = mark(...)` in `field second`, rồi đặt `second=20`.
6. `main` nhận kết quả `20`; lần đọc `Demo.first` sau đó không chạy lại initializer.

### 4.1. Xem bytecode gộp thành `<clinit>`

Sau khi biên dịch ví dụ:

~~~bash
javap -c -p 'InitOrder$Demo'
~~~

Tìm phần `static {};` ở cuối đầu ra `javap`. Mẫu bytecode quan trọng sẽ mang ý nghĩa:

~~~text
invokestatic mark(...)         // tính first
putstatic first                // first = 10
... invokevirtual println ...  // chạy static block
invokestatic mark(...)         // tính second
putstatic second               // second = 20
return
~~~

Mã đã kiểm tra trên OpenJDK 21 cho thấy phần `static {};` chứa cả hai `putstatic` và lời gọi in của khối giữa, đúng thứ tự. Thứ tự **hành vi** là do ngôn ngữ quy định; các chỉ số constant pool, offset và opcode tối ưu cụ thể có thể khác giữa compiler/JDK.

### 4.2. Forward reference: luật compile time và giá trị runtime

Đoạn dưới **không biên dịch được** vì đọc bằng *simple name* một trường được khai báo phía sau trong initializer:

~~~java
class IllegalForward {
    static int first = later; // illegal forward reference
    static int later = 7;
}
~~~

Nhưng giới hạn forward reference không cấm một phương thức như `readSecond()` đọc field sau khi JVM đã cho phép gọi phương thức ấy. Bởi vậy `InitOrder.Demo` ở trên **biên dịch được** nhưng vẫn thấy `second=0` trong lúc initialization đang dang dở. Có thể dùng qualified field access hoặc đường gọi gián tiếp để vượt trường hợp compile-time bị cấm, song việc ấy **không làm field được gán sớm hơn**.

**Kinh nghiệm:** Nếu các static fields phụ thuộc nhau, viết luồng khởi tạo đơn giản theo đúng thứ tự và tránh callback ở giữa. Đừng thiết kế logic đúng sai dựa trên việc một field khác tình cờ còn giá trị mặc định.

## 5. Hằng biên dịch và mã khởi tạo tĩnh

`static final int RETRIES = 3` và `static final String LABEL = "ready"` là **constant variables**: `final`, kiểu primitive/`String`, giá trị là *constant expression*. Chúng có thể dùng thuộc tính `ConstantValue` và được inline vào mã bên gọi. `static final Integer BOXED = 3` hoặc `static final int SIZE = Integer.parseInt("3")` không phải constant variables và cần initializer ở runtime. `ConstantValue` được gán **trong initialization trước `<clinit>`**, sau preparation đặt giá trị mặc định.

Việc chỉ thấy `static final` chưa đủ để kết luận có mã `<clinit>` hay một phép đọc có kích hoạt initialization. Bài **Các thao tác không kích hoạt khởi tạo** trình bày riêng ví dụ compile-time constant, `Integer`, inlining và binary compatibility.

## 6. Khi nào JVM đi vào `<clinit>`?

Một lớp có thể đã được load/link nhưng mã static chỉ được thực thi khi có yêu cầu **initialization**. Các điểm kích hoạt phổ biến: `new`, `getstatic` đọc nonconstant field, `putstatic` ghi field, `invokestatic` gọi phương thức static của **declaring type**, hoặc API như `Class.forName(name, true, loader)`. Ngược lại, chỉ thực hiện `T.class`, `new T[5]` hay `Class.forName(name, false, loader)` không tự yêu cầu khởi tạo `T`.

Các bài **Các thao tác chủ động kích hoạt khởi tạo** và **Các thao tác không kích hoạt khởi tạo** hướng dẫn chi tiết về trigger, reflection, MethodHandle và constant inlining. Ở đây, điểm chính là phân biệt **thời điểm có class file** với **thời điểm thực thi mã `<clinit>`**.

## 7. Class cha và interface trong quy trình initialization

Trước khi chạy initializer tĩnh thông thường của một class, JVM phải initialize superclass và các superinterface **có khai báo default method** theo thuật toán quy định. Nhưng initialize một interface riêng lẻ không tự động kéo theo initialization mọi superinterface; chỉ quan hệ `implements` cũng không khiến tất cả interface chạy mã static.

Bài **Khởi tạo lớp cha và thứ tự thực hiện static initializer** cùng bài **Khởi tạo interface và ảnh hưởng của default method** cho những ví dụ có output riêng để kiểm chứng thứ tự giữa các kiểu.

## 8. Đồng bộ khởi tạo và đọc giá trị dở dang

JVM điều phối initialization theo **runtime class identity** (binary name và defining loader); một thread đang khởi tạo sẽ khiến thread khác cần cùng class phải chờ. Khi **chính thread đó** yêu cầu khởi tạo lại cùng class theo một vòng gọi, JVM không chạy lại `<clinit>` từ đầu. Field chưa được gán có thể vẫn là `0` hoặc `null`. Đồng bộ thành công công bố trạng thái ban đầu, nhưng không tự làm các phép ghi mutable static về sau trở nên thread-safe.

Hai bài **Đồng bộ khởi tạo lớp giữa nhiều luồng** và **Khởi tạo đệ quy, phụ thuộc vòng và giá trị chưa hoàn thiện** tập trung vào bảo đảm happens-before, vòng A → B → A và deadlock.

## 9. Nếu `<clinit>` thất bại

Static initializer ném exception chưa được xử lý có thể khiến class trở thành **erroneous**. Lần đầu JVM bọc throwable không thuộc `Error` bằng `ExceptionInInitializerError`; nếu throwable là `Error` thì có thể chuyển tiếp chính lỗi đó. Các yêu cầu khởi tạo sau đối với **cùng runtime class** gặp `NoClassDefFoundError` thay vì chạy lại `<clinit>`.

Vì thế hãy tìm nguyên nhân đầu tiên trong stack trace; tránh đặt công việc I/O hoặc thao tác cần retry trong static initializer. Bài **ExceptionInInitializerError và trạng thái khởi tạo thất bại** có quy trình debug chuyên sâu.

## 10. Cú pháp và giới hạn của khối `static`

Khối `static`:

~~~java
class StaticRules {
    private static final java.util.Map<String, Integer> CODES;

    static {
        java.util.Map<String, Integer> values = new java.util.HashMap<>();
        values.put("ok", 200);
        values.put("missing", 404);
        CODES = java.util.Map.copyOf(values);
    }

    static int codeOf(String key) {
        return CODES.getOrDefault(key, -1);
    }
}
~~~

Đây là đoạn **class minh họa** biên dịch được trên Java 17+, không khai báo `main`. Cách này hữu ích khi cần nhiều câu lệnh để tạo trạng thái static cuối cùng; `Map.copyOf` giúp tránh caller sửa trực tiếp trạng thái sau khởi tạo. Để chạy thử từ một chương trình khác, gọi `StaticRules.codeOf("ok")` và sẽ nhận `200`.

Các giới hạn quan trọng:

- Khối `static` không được dùng `return`; không có `this`/`super` của instance và không thể trực tiếp truy cập instance field/method như thể đã có đối tượng.
- Khối static phải **có khả năng complete normally** theo phân tích compile-time; viết một vòng vô hạn hoặc `throw` chắc chắn không có đường thoát sẽ gặp giới hạn JLS. Một phương thức được gọi từ initializer vẫn có thể ném lỗi ở runtime như `FailureCase`.
- Checked exceptions từ static initializer phải được xử lý trong khối hoặc chuyển thành unchecked exception; static initializer không có `throws` để khai báo.
- Interface **không cho khai báo `static { ... }` theo cú pháp Java**, nhưng có thể có các field initializer bằng biểu thức gọi phương thức, và compiler có thể tạo `<clinit>` cho interface ấy.
- Enum, record và các lớp do compiler/framework tạo vẫn có quy tắc class initialization; chi tiết code sinh ra có thể nhiều hơn dòng nguồn. Dùng `javap -c -p` để quan sát đúng artifact đang chạy.
- Dù JVM thường gộp các static initializers trong một `<clinit>`, compiler tối ưu hằng và đoạn mã khác có thể khiến kết quả bytecode không khớp một-một với từng dòng Java. Chú ý **hành vi do đặc tả quy định**, không khẳng định mọi compiler phải sinh bytecode giống nhau.

## 11. Chọn static field initializer hay static block?

| Nhu cầu | Cách viết thường rõ nhất | Điều cần cân nhắc |
| --- | --- | --- |
| Giá trị độc lập, gọn | `static final int LIMIT = 100;` | Compile-time constant có thể bị inline vào client |
| Cần gọi phương thức tính giá trị | `static final Config DEFAULT = createDefault();` | Factory được gọi lúc class initialize; có thể ném lỗi |
| Cần nhiều bước, ràng buộc thứ tự | `static { ... }` | Giữ đoạn ngắn, rõ exception và dependency |
| Cấu hình có thể thất bại hoặc phụ thuộc môi trường | Explicit bootstrap / dependency injection | Tránh làm cả class unusable do lỗi init một lần |
| Chi phí tạo resource lớn nhưng ít khi cần | Lazy holder hoặc lazy initialization có kiểm soát | Xử lý close/lifetime, concurrency, lỗi và cleanup riêng |

### 11.1. Initialization-on-demand holder: dựa trên chính cơ chế `<clinit>`

~~~java
public final class LazyService {
    private LazyService() { }

    private static final class Holder {
        static final LazyService INSTANCE = new LazyService();
    }

    public static LazyService instance() {
        return Holder.INSTANCE;
    }
}
~~~

`LazyService.instance()` là static method nên sẽ initialize `LazyService` nếu cần. Nhưng `Holder` là **class khác**: `Holder.INSTANCE` được khởi tạo khi `Holder` lần đầu active use. JVM đảm bảo phối hợp initialization giữa thread cho `Holder`; ví dụ này minh họa lazy singleton đơn giản mà không cần tự viết double-checked locking.

Giới hạn: instance sẽ tồn tại theo loader/lifetime của lớp, không có cơ chế đóng resource tự động; constructor nếu ném exception sẽ khiến `Holder` erroneous và không có retry trong cùng loader. Tránh áp dụng mẫu này cho resource cần vòng đời dừng/mở lại linh hoạt nếu chưa bổ sung cơ chế quản lý.

## 12. Checklist đọc lỗi hoặc phân tích `<clinit>`

Khi gặp một bug static initialization, làm theo thứ tự:

1. **Chỉ đúng runtime class:** tên đầy đủ, defining loader, module, JDK/runtime và điều kiện launcher. Cùng tên nhưng loader khác có thể có trạng thái riêng.
2. **Tìm trigger đầu tiên:** `new`, `getstatic/putstatic`, `invokestatic`, `Class.forName(..., true, ...)`, framework reflection hay lớp con kéo theo superclass/default-method interface.
3. **Đọc thứ tự mã nguồn:** mọi static field initializer và `static{}` theo thứ tự; đánh dấu dependency tới class khác. Phân biệt constant variables với nonconstant static fields.
4. **Đọc bytecode khi cần:** `javap -c -p ClassName`; xem phần `static {};` tương ứng `<clinit>`, các lệnh `getstatic`/`putstatic`, và `ConstantValue` trong `javap -v`. Đừng suy ra từ tên trường rằng field chắc chắn có `ConstantValue`.
5. **Đọc cause đầu tiên:** `ExceptionInInitializerError.getCause()` hoặc `getException()` (API lịch sử), log sớm nhất; nếu chỉ thấy `NoClassDefFoundError`, tìm failure trước đó cùng loader.
6. **Kiểm tra vòng phụ thuộc và blocking:** class A gọi B trong lúc A init, B đọc lại A; khóa, thread, kết nối bên ngoài, I/O trong `static{}`.
7. **Thiết kế lại nếu cần:** giảm side effect, đưa việc có thể fail vào startup quản lý rõ ràng, tránh trạng thái static mutable chia sẻ không đồng bộ, tái biên dịch consumer khi đổi compile-time constants.

Các lệnh hữu ích khi có JDK tools:

~~~bash
javac --release 17 InitOrder.java
javap -c -p 'InitOrder$Demo'
javap -v 'ConstantCase$Config'
java -Xlog:class+init=info InitOrder
~~~

`-Xlog:class+init=info` là logging của **HotSpot/OpenJDK hỗ trợ unified logging** và có thể in rất nhiều thông tin; tên tag/đầu ra không phải cú pháp chuẩn JLS cho mọi JVM. Nếu tùy môi trường, kiểm tra `java -Xlog:help`. `javap` là công cụ JDK đọc class file; có thể phát hiện `ConstantValue` và `static {};` ngay cả khi chưa chạy chương trình.

## 13. Điểm kiểm tra khi đọc `<clinit>`

Đọc static field initializers và `static {}` **theo thứ tự nguồn**, kiểm tra `ConstantValue`, dùng `javap -c -p` để thấy bytecode thường được in ở mục `static {};`, và phân biệt hoạt động **loading** với lúc mã thực sự chạy. Số khối `static` trong source không phải số phương thức `<clinit>` trong class file.

## 14. Câu hỏi tự kiểm tra

1. Nếu `static int a = 1; static { a++; } static int b = a * 2;` thì sau init có `a=2`, `b=4`. Giải thích theo thứ tự nguồn.
2. Vì sao `static final String LABEL = "ready";` không buộc class chủ sở hữu initialize khi client in hằng, còn `static final Integer BOXED = 42;` có thể buộc? Trả lời bằng điều kiện **constant variable**.
3. Vì sao `new ClassName[5]` và `ClassName.class` có thể chưa kích hoạt `<clinit>`?
4. Sau khi một static block ném `IllegalStateException` trong lần init đầu, vì sao lần sau cùng loader có thể thấy `NoClassDefFoundError`?
5. Một plugin reload tạo defining loader mới cho cùng tên lớp: static initializer có thể chạy lại không? **Có**, vì đó là runtime class identity mới, trong khi lớp cũ nếu còn referenced vẫn là entity khác.
6. Nếu trường nonconstant được khai báo sau block, vì sao block có thể đọc `0` qua phương thức gọi gián tiếp dù sau cùng trường là `20`?
7. Vì sao chạy `javap -c -p` và tìm phần `static {};` giúp giải thích thứ tự field initializer và static block?

## 15. Tài liệu đặc tả và API chuẩn

- [JLS 12.4 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.4): active use, thứ tự superclass/superinterface, synchronization, erroneous state.
- [JLS 8.3.2, 8.3.3 — Field Initialization và Forward References](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.3.2): field initializer và giới hạn đọc field trước khai báo.
- [JLS 8.7 — Static Initializers](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.7): quy tắc cú pháp khối `static`.
- [JLS 4.12.4 — Constant Variables](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.12.4): điều kiện hằng compile time.
- [JVMS 5.4.2 — Preparation](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.4.2) và [JVMS `5.5 — Initialization](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.5): giá trị mặc định, `ConstantValue`, kích hoạt initialization.
- [JVMS 2.9.2 — Class and Interface Initialization Methods](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.9.2): tên/mô tả method `<clinit>`.
- [ClassLoader API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html) và [Class.forName API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)): phân biệt loading với yêu cầu initialization.

**Ghi nhớ:** Static field initializers và static blocks xác định những **hành động khởi tạo** của lớp trong thứ tự được JLS quy định; compiler thường tổng hợp thành `<clinit>` để JVM chạy **khi lớp được initialize**, dưới cơ chế đồng bộ và xử lý lỗi của JVMS. Hiểu đúng *khi nào*, *theo thứ tự nào* và *với class identity nào* quan trọng hơn việc ghi nhớ tên phương thức đặc biệt.
