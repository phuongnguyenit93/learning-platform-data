# Phân biệt liên kết lớp với khởi tạo lớp trong Java

## 1. Vấn đề cần phân biệt

Khi một ứng dụng Java nhắc đến một lớp, JVM không nhất thiết chạy ngay các câu lệnh `static` của lớp đó. Hai giai đoạn thường bị nhầm là **liên kết lớp (linking)** và **khởi tạo lớp (initialization)**:

- **Liên kết**: JVM kiểm tra và chuẩn bị một lớp/interface đã được nạp để nó có thể tham gia thực thi. Ba hoạt động liên quan gồm **verification**, **preparation** và **resolution**.
- **Khởi tạo**: JVM thực thi logic khởi tạo biến `static` và khối `static { ... }` của lớp (với interface là các biểu thức khởi tạo trường), tương ứng phương thức khởi tạo đặc biệt `<clinit>` nếu class file có phương thức này.

Nhìn tổng quan:

```text
Tên lớp + ClassLoader
        │
        ▼
Loading (nạp): tìm/định nghĩa class từ bytecode
        │
        ▼
Linking (liên kết)
   ├─ Verification: kiểm tra class file và ràng buộc bytecode
   ├─ Preparation: tạo static fields, đặt giá trị mặc định
   └─ Resolution: xử lý symbolic references khi cần
        │
        ▼
Initialization (khởi tạo)
   ├─ đảm bảo superclass (và một số superinterface) cần thiết đã init
   ├─ chạy initializer của các trường static và khối static
   └─ hoàn tất hoặc chuyển sang trạng thái lỗi
        │
        ▼
Sử dụng lớp và các thành viên
```

**Sơ đồ chỉ thể hiện quan hệ logic, không phải lịch trình tuyệt đối của JVM.** Theo đặc tả, một lớp phải được nạp trước khi liên kết, và **verification + preparation phải hoàn tất trước khi khởi tạo**. Riêng **resolution được phép trì hoãn**: các tham chiếu có thể chỉ được resolve lúc thật sự sử dụng, kể cả sau khi lớp đã khởi tạo. Vì vậy, không suy ra rằng mọi dependency đã resolve xong trước dòng đầu tiên của `static`.

Cách nhớ thực dụng: **linking chuẩn bị một định nghĩa lớp để JVM sử dụng; initialization thực thi code khởi tạo của chính lớp đó**.

## 2. Linking gồm những hoạt động gì?

**Verification** kiểm tra class file và an toàn kiểu bytecode; lỗi điển hình là `ClassFormatError` hoặc `VerifyError`. **Preparation** tạo các field `static` với giá trị mặc định (`0`, `false`, `null`), chưa thực thi phép gán hay `static` block của ứng dụng. **Resolution** tra cứu class/field/method được mô tả bằng symbolic reference và kiểm tra điều kiện liên kết; nó có thể xảy ra sớm hoặc muộn. Các hằng có `ConstantValue` được gán ở bước riêng khi bắt đầu **initialization** theo JVMS §5.5, không được đồng nhất với việc chạy initializer Java trong preparation.

Ví dụ `static int count = 42;` có giá trị mặc định `0` sau preparation và nhận `42` khi initializer được thực thi. `static final int LIMIT = 42;` là constant variable, có thể được compiler nhúng vào nơi sử dụng; chỉ đọc nó không bắt buộc init kiểu khai báo. Hai công việc có thể đều hoàn thành khi chưa có object nào được tạo.

## 3. Initialization thực sự thực hiện gì?

Lúc khởi tạo lớp, JVM đảm bảo các điều kiện bắt buộc (như khởi tạo superclass trước), rồi thực thi các phép gán/biểu thức khởi tạo trường `static` và khối `static { ... }` **theo thứ tự xuất hiện trong mã nguồn**, tương ứng logic phương thức đặc biệt `<clinit>` được compiler tạo ra nếu cần.

```java
static int a = calculateA();    // bước khởi tạo do chương trình viết
static { log("block 1"); }      // khối khởi tạo
static int b = calculateB();    // bước khởi tạo tiếp theo
```

Những biểu thức này có thể thực hiện I/O, gọi phương thức, thay đổi trạng thái và ném exception. Do đó initialization có side effect có thể quan sát được; linking tự nó không phải là việc chạy static initializer.

**Đừng nhầm ba cơ chế:**

- `<clinit>`: phương thức khởi tạo **lớp/interface**; JVM thực thi ở giai đoạn initialization, không gọi trực tiếp từ Java source.
- `<init>`: constructor **đối tượng**; chạy khi tạo instance sau khi các điều kiện khởi tạo lớp đã được thỏa mãn.
- Khởi tạo field **instance**: một phần của việc khởi tạo đối tượng, không xảy ra chỉ vì lớp đã được liên kết/khởi tạo.

Một lớp không có logic khởi tạo `static` riêng có thể không có `<clinit>` trong class file; điều đó không có nghĩa JVM bỏ qua hoàn toàn quy tắc trạng thái khởi tạo cho lớp.

## 4. Khi nào JVM yêu cầu initialization?

Initialization được yêu cầu khi tạo instance `new T()`, gọi phương thức `static` do T khai báo, đọc/ghi `static` field được khai báo bởi T (riêng việc đọc constant variable đã inline không kích hoạt), hoặc dùng một số API reflection như `Class.forName(name)`.

Ngược lại, chỉ lấy `T.class`, tạo `new T[10]`, gọi `ClassLoader.loadClass` hay `Class.forName(name, false, loader)` **không tự** yêu cầu init T. Với field kế thừa, hãy xét **lớp thực sự khai báo field**, không chỉ tên type ở phía trái source. Bài tiếp theo phân tích chi tiết các trigger, thứ tự cha/con và trường hợp đa luồng.

## 5. Ví dụ chạy được: lớp được nạp nhưng chưa khởi tạo

Tạo tệp `LifecycleDemo.java` dưới đây (Java 17+):

```java
public class LifecycleDemo {
    static class Parent {
        static {
            System.out.println("Parent initialized");
        }

        static int count = 7;
    }

    static class Child extends Parent {
        static {
            System.out.println("Child initialized");
        }

        static void ping() {
            System.out.println("Child.ping");
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("A: class literal");
        Class<?> token = Child.class;

        System.out.println("B: load without initialization");
        Class<?> loaded = Class.forName(
                Child.class.getName(),
                false,
                LifecycleDemo.class.getClassLoader()
        );

        System.out.println("same Class object: " + (token == loaded));

        System.out.println("C: inherited static field");
        System.out.println("count=" + Child.count);

        System.out.println("D: Child static method");
        Child.ping();

        System.out.println("E: done");
    }
}
```

Chạy trong terminal:

```bash
javac LifecycleDemo.java
java LifecycleDemo
```

Stdout chính xác khi chạy lần đầu trong JVM mới:

```text
A: class literal
B: load without initialization
same Class object: true
C: inherited static field
Parent initialized
count=7
D: Child static method
Child initialized
Child.ping
E: done
```

**Giải thích thứ tự:**

1. Lấy `Child.class` và dùng `Class.forName(..., false, ...)` trả đối tượng `Class` cho cùng lớp; cả hai không yêu cầu chạy `Child.<clinit>`.
2. `Child.count` được khai báo trong `Parent`. Việc đọc trường đó kích hoạt initialization của **Parent**, do đó in `Parent initialized` trước `count=7`; không kích hoạt initialization của Child.
3. Gọi `Child.ping()` là active use của phương thức `static` khai báo tại Child. JVM khởi tạo Child (Parent đã xong) rồi mới chạy thân `ping()`.

Ví dụ giúp quan sát **thời điểm initialization**, không đo trực tiếp thời điểm các bước verification/preparation/resolution đã được JVM chọn thực hiện.

## 6. Quan hệ superclass, interface và ClassLoader

### 6.1. Superclass trước subclass

Khi khởi tạo một class, JVM cần khởi tạo các superclass chưa khởi tạo trước class đó. Vì thế lần đầu `new Child()` có thể chạy initializer của Parent rồi Child. Một **static field được khai báo tại Parent** chỉ khởi tạo Parent ngay cả khi source viết `Child.field` (như mục 6).

Khi khởi tạo class, đặc tả Java hiện đại còn quy định khởi tạo các **superinterface khai báo default method** thích hợp trước class đó. Không được nói rằng *mọi* interface mà class implements đều khởi tạo trước class; interface không có default method có thể chưa khởi tạo.

### 6.2. Interface khác class

Một interface được khởi tạo khi có tác nhân yêu cầu, chẳng hạn truy cập một trường `static` **không phải compile-time constant** do nó khai báo. Initialization của interface **không tự khởi tạo toàn bộ superinterface**.

Trong interface, các field mặc nhiên là `public static final`, nhưng không phải tất cả đều là compile-time constants. Ví dụ:

```java
interface Flag {
    int CONSTANT = 10;
    int RUNTIME_VALUE = Integer.parseInt("20");
}
```

Đọc `Flag.CONSTANT` không bắt buộc initialize Flag; đọc `Flag.RUNTIME_VALUE` yêu cầu initialize Flag.

### 6.3. Một binary name có thể có nhiều trạng thái init

Với cơ chế plugin hoặc container sử dụng nhiều class loader, cùng binary name `com.example.Plugin` được định nghĩa bởi hai defining loaders khác nhau tương ứng với **hai runtime classes**. Chúng có các `static` field và trạng thái initialization độc lập. JVM không dùng bảng "đã init" duy nhất theo **tên chữ** của lớp.

Tương tự, việc cùng một `Class<?>` đã initialization thành công được chia sẻ giữa các thread trong JVM; gọi lặp một `static` method không chạy `<clinit>` lại.

## 7. So sánh nhanh để tránh nhầm

| Câu hỏi | Linking | Initialization |
|---|---|---|
| Mục đích | Kiểm tra và chuẩn bị class để JVM sử dụng, resolve tham chiếu khi cần | Thực thi logic khởi tạo `static` của class/interface |
| Bắt buộc đã loading? | Có | Có |
| Chạy khối `static { ... }`? | Không | Có, khi class có khối này |
| Tạo và gán mặc định cho `static` fields? | Có, ở preparation | Giá trị có thể được thay bằng các initializer |
| Có thể tạo lỗi? | `VerifyError`, `LinkageError` như `NoSuchMethodError` | `ExceptionInInitializerError`, trạng thái init lỗi |
| Thời điểm | Verification/preparation trước initialization; resolution có thể trì hoãn | Theo các điều kiện active use |
| Có chạy lại khi gọi method static lần hai? | Thường không phải việc chạy lại toàn bộ linking cho mỗi call | Không chạy lại `<clinit>` đã hoàn tất |
| Có thể quan sát trực tiếp? | Qua bytecode, lớp được load, lỗi linkage, công cụ VM | Qua side effect của static initializer và trạng thái lỗi |

## 8. Câu hỏi tự kiểm tra

1. **`Class.forName("x.Y", false, loader)` có bắt buộc chạy `Y.<clinit>` không?** Không; tham số `false` không yêu cầu initialization.
2. **JVM có được khởi tạo class chưa verification/preparation không?** Không; cả hai phải hoàn tất trước initialization.
3. **Mọi symbolic reference phải resolve trước dòng đầu của `static` không?** Không; resolution có thể lazy và còn tiếp tục sau initialization.
4. **`static int n = 5` có giá trị gì tại thời điểm preparation?** Giá trị mặc định `0`; phép gán `5` thuộc initialization.
5. **`static final int N = 5` khi dùng ở lớp khác có bắt buộc init lớp khai báo không?** Không; đó là constant variable và có thể được inline.
6. **Đọc `Sub.field` sẽ init Sub hay Super nếu `field` khai báo trong Super?** Chỉ class thực sự khai báo field là Super phải init khi truy cập field không phải constant variable.
7. **Hai ClassLoader định nghĩa hai class cùng tên có dùng chung một lần `<clinit>` không?** Không; là hai runtime classes khác nhau.
8. **Lần đầu initialization thất bại, gọi lại có thực thi `<clinit>` lần nữa không?** Không; runtime class chuyển sang trạng thái erroneous và sử dụng tiếp sẽ thất bại.

## Tài liệu chuẩn để học sâu

- [Java Language Specification, Java SE 26, Chương 12 — Execution](https://docs.oracle.com/javase/specs/jls/se26/html/jls-12.html), đặc biệt `12.2 Loading, `12.3 Linking và `12.4 Initialization: định nghĩa và những sự kiện kích hoạt initialization.
- [Java Virtual Machine Specification, Java SE 25, Chương 5 — Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html), đặc biệt `5.4 Linking và `5.5 Initialization: quy tắc verifier, preparation, thời điểm resolution, đồng bộ hóa initialization.
- [Java Class API — forName](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Class.html): overload `initialize=true/false`.

Khi debug hành vi ClassLoader, hãy xác định **runtime class nào** đang được nói đến, **lớp đó đã load/link tới mức nào**, và **thao tác nào thực sự yêu cầu initialization**. Đây là cách giải thích đúng những trường hợp đã có `Class<?>` nhưng chưa thấy static initializer chạy, hoặc initialization ném lỗi dù bytecode trước đó đã được JVM chấp nhận.
