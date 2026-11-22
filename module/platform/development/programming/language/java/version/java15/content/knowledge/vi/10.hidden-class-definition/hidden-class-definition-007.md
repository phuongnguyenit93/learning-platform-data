# Tham số `initialize` và thời điểm khởi tạo lớp ẩn (Java 15+)

## 1. Câu hỏi trọng tâm: lớp ẩn được khởi tạo lúc nào?

Từ **Java 15**, `MethodHandles.Lookup.defineHiddenClass` cho phép tạo một **hidden class** (lớp ẩn) từ bytecode `.class`. Cách này phù hợp với những thư viện hoặc runtime cần sinh lớp phụ trợ ở thời gian chạy mà không yêu cầu các lớp khác tìm lớp ấy theo tên nhị phân thông thường.

Phương thức trọng tâm:

```java
MethodHandles.Lookup hiddenLookup =
        lookup.defineHiddenClass(
                classBytes,
                initialize,
                options
        );
```

Trong đó:

- `classBytes`: mảng `byte[]` chứa một class file hợp lệ, có tên lớp trong **cùng package** với lớp của `lookup`.
- `initialize`: giá trị `boolean` điều khiển việc **có khởi tạo ngay lớp ẩn trong lần gọi phương thức này hay không**.
- `options`: các tùy chọn `MethodHandles.Lookup.ClassOption...`, ví dụ `NESTMATE` hoặc `STRONG`; chúng có mục đích khác với `initialize`.
- Giá trị trả về là một **`MethodHandles.Lookup` mới**, có lookup class chính là lớp ẩn vừa tạo. Lấy đối tượng `Class<?>` qua `hiddenLookup.lookupClass()`.

**Hai trường hợp cần thuộc:**

- **`initialize=true`:** JVM liên kết (*link*) rồi **khởi tạo lớp ẩn trước khi `defineHiddenClass` trả về thành công**. Mã khởi tạo biến `static` và khối `static { ... }` (nếu có) được thực thi trong giai đoạn này.
- **`initialize=false`:** JVM vẫn **định nghĩa và liên kết lớp ẩn** nhưng **không chủ động khởi tạo lớp ẩn chỉ vì lần gọi `defineHiddenClass` đó**. Việc khởi tạo có thể xảy ra **sau này**, khi một thao tác thực sự yêu cầu lớp được khởi tạo.

`false` **không** có nghĩa “cấm khởi tạo mãi mãi”, “chỉ tải bytecode mà không kiểm tra” hay “không bao giờ chạy `static`”. Nó chỉ trì hoãn bước khởi tạo do `defineHiddenClass` thực hiện.

API này được chuẩn hóa từ **Java 15** và tiếp tục được hỗ trợ trong JDK hiện đại. Không cần bật chế độ preview.

## 2. Phân biệt `define`, `link` và `initialize`

Đây là ba giai đoạn có vai trò khác nhau trong JVM:

| Giai đoạn | Điều xảy ra | Khối `static { ... }` có chạy không? |
| --- | --- | --- |
| **Định nghĩa (definition)** | JVM tạo định danh lớp từ cấu trúc bytecode; với hidden class, JVM tạo danh tính lớp riêng không thể tra theo tên nhị phân bình thường. | Chưa phải lý do tự chạy `<clinit>`. |
| **Liên kết (linking)** | JVM xác minh, chuẩn bị các thành phần cần thiết, có thể giải quyết tham chiếu ký hiệu theo quy định JVM. | Việc chuẩn bị `static` không đồng nghĩa chạy biểu thức khởi tạo `static`. |
| **Khởi tạo (initialization)** | JVM thực thi phương thức khởi tạo lớp `<clinit>` được biên dịch từ khối `static` và các khởi tạo trường `static`. | **Có**, nếu lớp có mã cần thực thi. |

**`defineHiddenClass` thực hiện định nghĩa và liên kết lớp ẩn trong cả hai trường hợp `initialize`.** Tham số này chỉ quyết định có yêu cầu **bước khởi tạo** ngay trong lời gọi hay không.

Ví dụ:

```java
class Demo {
    static int counter = createCounter();

    static {
        System.out.println("static block");
    }

    private static int createCounter() {
        System.out.println("static field initialization");
        return 42;
    }
}
```

Mã `createCounter()` và `static block` thuộc hoạt động khởi tạo lớp. Trong Java, khởi tạo trường `static` và khối `static` chạy **theo thứ tự khai báo trong mã nguồn** khi khởi tạo lớp xảy ra. **Preparation** có thể cấp giá trị mặc định cho trường `static` nhưng không đồng nghĩa đã thực thi `createCounter()`.

Nếu lớp không có mã khởi tạo có hiệu ứng quan sát được, bạn có thể không thấy khác biệt trên console giữa `true` và `false`. Vì vậy, ví dụ kiểm chứng thời điểm khởi tạo nên đặt thông điệp rõ trong `<clinit>`.

## 3. Ví dụ chạy được: quan sát ba cách khởi tạo

Ví dụ dùng **hai file Java trong cùng thư mục, cùng package mặc định**. File `InitTarget.java` chỉ cung cấp bytecode của lớp làm mẫu; chương trình chính đọc file `InitTarget.class` bằng `Files.readAllBytes`, **không chủ động tạo đối tượng hoặc gọi phương thức của lớp `InitTarget` thông thường**.

### File 1: `InitTarget.java`

```java
class InitTarget {
    static int value = compute();

    private static int compute() {
        System.out.println("  <clinit> executes");
        return 42;
    }

    static int value() {
        return value;
    }
}
```

Lời gọi `compute()` được đặt trong biểu thức khởi tạo `static`. Khi JVM khởi tạo **một bản lớp ẩn** từ bytecode này, thông điệp `<clinit> executes` sẽ xuất hiện đúng một lần nếu khởi tạo thành công.

### File 2: `HiddenInitializationDemo.java`

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.nio.file.Files;
import java.nio.file.Path;

public class HiddenInitializationDemo {
    public static void main(String[] args) throws Throwable {
        byte[] classBytes =
                Files.readAllBytes(Path.of("InitTarget.class"));
        MethodHandles.Lookup host = MethodHandles.lookup();

        System.out.println("=== initialize=false ===");
        MethodHandles.Lookup lazy =
                host.defineHiddenClass(classBytes, false);
        Class<?> lazyClass = lazy.lookupClass();
        System.out.println(
                "after define: hidden=" + lazyClass.isHidden()
        );

        MethodHandle getter = lazy.findStatic(
                lazyClass,
                "value",
                MethodType.methodType(int.class)
        );
        System.out.println("after findStatic");
        System.out.println(
                "first invoke=" + (int) getter.invokeExact()
        );
        System.out.println(
                "second invoke=" + (int) getter.invokeExact()
        );

        System.out.println("=== initialize=true ===");
        MethodHandles.Lookup eager =
                host.defineHiddenClass(classBytes, true);
        System.out.println(
                "after define: hidden=" +
                        eager.lookupClass().isHidden()
        );

        System.out.println("=== ensureInitialized ===");
        MethodHandles.Lookup explicit =
                host.defineHiddenClass(classBytes, false);
        System.out.println("after define(false)");

        explicit.ensureInitialized(explicit.lookupClass());
        System.out.println("after ensureInitialized");

        explicit.ensureInitialized(explicit.lookupClass());
        System.out.println("after second ensureInitialized");
    }
}
```

**Cách chạy:** lưu đúng hai file với tên như trên, mở terminal tại **thư mục chứa file**, biên dịch và chạy:

```bash
javac --release 15 -encoding UTF-8 InitTarget.java HiddenInitializationDemo.java
java HiddenInitializationDemo
```

`--release 15` yêu cầu bộ biên dịch JDK tương thích tạo mã và kiểm tra API theo Java 15. Có thể dùng JDK 17+ để thực hiện, hoặc dùng JDK 15 phù hợp. Khi đã chọn JDK đích, cần bảo đảm môi trường chạy hỗ trợ class file được sinh ra.

**Đầu ra đã kiểm tra thực tế trên JDK 24 sau khi biên dịch với `--release 15`:**

```text
=== initialize=false ===
after define: hidden=true
after findStatic
  <clinit> executes
first invoke=42
second invoke=42
=== initialize=true ===
  <clinit> executes
after define: hidden=true
=== ensureInitialized ===
after define(false)
  <clinit> executes
after ensureInitialized
after second ensureInitialized
```

Đây là đầu ra của ba **lớp ẩn khác nhau** tạo từ cùng mảng bytecode. Mỗi lần `defineHiddenClass` tạo **danh tính lớp ẩn mới**; vì vậy mỗi lớp ẩn có trạng thái khởi tạo riêng và có thể in thông điệp `<clinit>` một lần.

### 3.1. Trường hợp `initialize=false`: khởi tạo khi dùng

Trong phần đầu:

1. `host.defineHiddenClass(classBytes, false)` đã định nghĩa và liên kết một lớp ẩn, rồi trả `Lookup`; **chưa chạy `<clinit>` của lớp đó**.
2. `lazy.lookupClass()` lấy `Class<?>` đại diện cho lớp ẩn; `isHidden()` chỉ trả thông tin lớp, không làm mã khởi tạo lớp chạy.
3. `lazy.findStatic(...)` tìm và tạo `MethodHandle` trỏ đến phương thức `static value()`. **Việc tạo handle chưa gọi phương thức**, nên trong ví dụ này `<clinit>` vẫn chưa chạy.
4. **Lời gọi `getter.invokeExact()` lần đầu** thực thi phương thức `static`. JVM phải khởi tạo lớp trước khi chạy phương thức; do đó console in `<clinit> executes` **trước** `first invoke=42`.
5. **Lời gọi `getter.invokeExact()` lần thứ hai** không chạy `<clinit>` thêm lần nữa, vì lớp đã khởi tạo thành công.

Không nên suy ra rằng **mọi** lời gọi API phản chiếu hay mọi loại `MethodHandle` đều không khởi tạo. Hành vi phụ thuộc API và thao tác cuối cùng; ví dụ này kiểm chứng riêng `lookupClass`, `findStatic` và **lần gọi** handle tới phương thức `static`.

### 3.2. Trường hợp `initialize=true`: khởi tạo trước khi trả kết quả

Trong phần thứ hai:

```java
MethodHandles.Lookup eager =
        host.defineHiddenClass(classBytes, true);
```

Thông điệp `<clinit> executes` xuất hiện **trước** `after define: hidden=true`. Lý do: JVM đã khởi tạo bản lớp ẩn này trong lời gọi `defineHiddenClass`. Khi phương thức trả về bình thường, lớp ẩn đã được khởi tạo.

Về hiệu năng và ngữ nghĩa, `initialize=true` có thể khiến **công việc trong khối `static` được thực hiện ngay**: tải cấu hình, tạo bảng dữ liệu, đăng ký callback hoặc chạy bất cứ hiệu ứng nào được viết trong class initializer. Không thể coi `defineHiddenClass(..., true)` chỉ là thao tác “chuẩn bị metadata”.

### 3.3. Trường hợp `false` + `ensureInitialized`: chủ động khởi tạo sau

Trường hợp thứ ba định nghĩa với `false` nhưng **chủ động yêu cầu** khởi tạo lúc đã sẵn sàng:

```java
MethodHandles.Lookup explicit =
        host.defineHiddenClass(classBytes, false);

Class<?> hiddenType = explicit.lookupClass();

// Thuc thi <clinit> neu lop chua khoi tao.
explicit.ensureInitialized(hiddenType);
```

`Lookup.ensureInitialized(Class<T>)` là API chuẩn từ Java 15. Nó bảo đảm lớp đã khởi tạo khi phương thức trả bình thường, **trừ trường hợp đặc biệt khi chính thread hiện tại đang khởi tạo lớp đó theo quy định JVM**. Nó yêu cầu lớp phải **accessible** từ `Lookup` đang dùng. Trong ví dụ, `explicit` là `Lookup` được trả về cho chính lớp ẩn nên có quyền phù hợp.

Lần `ensureInitialized` đầu thực thi `<clinit>`; lần thứ hai không chạy lại khởi tạo. Cách này hữu ích khi framework muốn **định nghĩa trước** một lớp ẩn, thiết lập dữ liệu hoặc đường gọi ở phía ngoài, rồi **kiểm soát thời điểm khởi tạo** trước khi đưa lớp vào sử dụng thực tế.

## 4. Những thao tác nào có thể kích hoạt khởi tạo?

Các lớp ẩn vẫn tuân theo quy tắc JVM cho thời điểm khởi tạo lớp. Những thao tác thường yêu cầu khởi tạo **một lớp cụ thể** gồm:

- **Tạo instance** của lớp (`new` hoặc gọi constructor tương ứng qua method handle/reflective API).
- **Gọi phương thức `static` do lớp đó khai báo**, như `getter.invokeExact()` trong ví dụ.
- **Gán hoặc đọc trường `static` không phải constant variable** do lớp đó khai báo (tùy thao tác và quy tắc JVM).
- **Gọi `Lookup.ensureInitialized(hiddenClass)`** từ `Lookup` có quyền truy cập phù hợp.
- Một số thao tác của reflection hoặc JVM có quy tắc riêng yêu cầu khởi tạo.

Các thao tác **không đủ để kết luận lớp đã khởi tạo** gồm:

- Chỉ **đọc bytecode** từ file bằng `Files.readAllBytes`.
- `defineHiddenClass(bytes, false)` trả về bình thường.
- Chỉ giữ đối tượng `Class<?>` hoặc gọi `Class.isHidden()` để xem metadata.
- Chỉ tạo `MethodHandle` bằng `findStatic` **trong ví dụ đã kiểm thử**, chưa `invoke`.

### 4.1. `static final` compile-time constant là ngoại lệ đáng chú ý

Không dùng một trường constant như dưới đây làm dấu hiệu khởi tạo lớp:

```java
class ConstantExample {
    static final int LIMIT = 10;

    static {
        System.out.println("class initialized");
    }
}
```

Trong mã Java thông thường, **truy cập một compile-time constant** như `LIMIT` có thể được biên dịch thành giá trị trực tiếp và **không kích hoạt khởi tạo lớp**. `static final` không tự động đồng nghĩa compile-time constant: một trường có giá trị tính ở runtime, ví dụ `static final int VALUE = calculate()`, có ngữ nghĩa khác.

Với hidden class không thể được lớp khác tham chiếu bằng tên nhị phân thông thường, nên việc dùng `MethodHandle` tới phương thức `static` hoặc `ensureInitialized` là cách kiểm chứng thời điểm khởi tạo rõ ràng hơn việc suy diễn từ truy cập trường hằng.

### 4.2. Lớp cha và thread khác cũng ảnh hưởng thứ tự

Khi một class được khởi tạo, JVM cần xử lý việc khởi tạo **superclass** theo quy tắc khởi tạo lớp. Vì vậy, trên thực tế có thể nhìn thấy hiệu ứng khởi tạo từ lớp cha trước khi chạy `<clinit>` của lớp ẩn.

Initialization cũng được JVM **đồng bộ hóa theo lớp**: nếu hai thread đồng thời yêu cầu khởi tạo cùng một danh tính lớp ẩn, JVM đảm bảo quá trình khởi tạo được điều phối theo quy tắc JVM; các thread khác có thể phải chờ. Không tự viết khóa để mô phỏng khởi tạo `static` một lần.

Sự phân biệt **mỗi lớp có một danh tính** rất quan trọng: ba lần `defineHiddenClass` từ cùng bytecode tạo ra **ba lớp khác nhau**, nên JVM có thể khởi tạo chúng độc lập. Duy nhất một lần khởi tạo thành công áp dụng cho **mỗi danh tính lớp**, không phải một lần cho cả tệp bytecode.

## 5. Hiểu đúng bản chất hidden class trước khi điều khiển `initialize`

### 5.1. Vì sao `Lookup` quan trọng?

`MethodHandles.lookup()` tạo `Lookup` gắn với lớp gọi nó và các quyền truy cập tương ứng. `defineHiddenClass` đòi hỏi `Lookup` có **full privilege access**, và class file được cung cấp phải mô tả lớp nằm trong **cùng package** với lookup class.

Trong ví dụ cả `InitTarget` và `HiddenInitializationDemo` đều ở **package mặc định**, nên yêu cầu package được đáp ứng. Với ứng dụng tổ chức theo package, đặt hai lớp mẫu và lớp gọi `defineHiddenClass` cùng package tương ứng.

`defineHiddenClass` trả một `Lookup` **mới dành cho lớp ẩn**. Ta dùng `lazy.lookupClass()` để lấy đối tượng `Class<?>` và `lazy.findStatic(...)` để lấy method handle đủ quyền truy cập thành viên đã định nghĩa.

`initialize` không quyết định quyền truy cập của `Lookup` và cũng không biến lớp ẩn thành lớp có thể tìm qua tên thông thường.

### 5.2. Lớp ẩn không được tra cứu qua tên nhị phân bình thường

Hidden class có **danh tính riêng**, cho phép truy cập qua `Class<?>`, `Lookup`, method handle hay reflection phù hợp. Nó **không được tìm bằng `Class.forName(hiddenClass.getName())`** như lớp bình thường vì tên báo cáo của hidden class không phải một tên nhị phân có thể nạp theo cơ chế đó.

Có thể kiểm tra:

```java
System.out.println(
        lazy.lookupClass().isHidden()
); // true
```

**Không nhầm** tên gốc của bytecode `InitTarget` với danh tính lớp ẩn vừa định nghĩa. JVM tạo một danh tính hidden class riêng ngay cả khi mảng `classBytes` giữ nguyên. Một `InitTarget` thông thường đã được class loader tải và một hidden class tạo từ bytecode tương tự là **hai class khác nhau**.

### 5.3. `NESTMATE` và `STRONG` không thay thế tham số `initialize`

Hai tùy chọn lớp ẩn thường được nhắc tới:

- `MethodHandles.Lookup.ClassOption.NESTMATE`: xác định quan hệ **nestmate** với nest của lookup class theo API, có ảnh hưởng đến quyền truy cập thành viên riêng tư.
- `MethodHandles.Lookup.ClassOption.STRONG`: xác định quan hệ giữ class và class loader theo hướng **strong**, ảnh hưởng đến khả năng hidden class được unload.

Đây là các quyết định về **quan hệ truy cập và vòng đời class**, không quyết định trực tiếp `<clinit>` chạy ngay hay chạy sau. Bạn vẫn chọn `initialize=true` hoặc `false` độc lập với chúng.

Ví dụ cú pháp:

```java
MethodHandles.Lookup hiddenLookup = host.defineHiddenClass(
        classBytes,
        false,
        MethodHandles.Lookup.ClassOption.NESTMATE
);
```

Đoạn trên là **minh họa API trong một ngữ cảnh đã có `host` và `classBytes`**, không phải chương trình độc lập. Trong trường hợp này, `initialize=false` vẫn có nghĩa không chủ động khởi tạo lớp ẩn ngay ở lời gọi định nghĩa.

## 6. Chọn `true` hay `false` trong ứng dụng thực tế

| Nhu cầu | Lựa chọn phù hợp | Hệ quả |
| --- | --- | --- |
| Cần lớp sẵn sàng với giá trị `static` đã khởi tạo ngay khi hàm định nghĩa trả về | `initialize=true` | `<clinit>` chạy trong `defineHiddenClass`; lỗi khởi tạo có thể phát sinh tại đây. |
| Chỉ cần định nghĩa/lấy `Lookup` trước, chưa muốn thực thi mã `static` | `initialize=false` | `<clinit>` chờ đến khi có thao tác kích hoạt khởi tạo. |
| Muốn định nghĩa trước, sau đó chọn một thời điểm chủ động khởi tạo | `false`, sau đó `lookup.ensureInitialized(hiddenClass)` | Tách rõ thời điểm định nghĩa và thời điểm thực thi `<clinit>`. |
| Định nghĩa xong rồi lập tức invoke phương thức `static` | Cả hai có thể hợp lệ | Với `false`, lần invoke đầu sẽ khởi tạo; với `true`, lớp đã khởi tạo trước đó. |
| Khối `static` có nhiều hiệu ứng phụ hoặc thao tác tốn tài nguyên | Xem lại thiết kế, chọn thời điểm phù hợp | Tham số `initialize` chỉ chọn **thời điểm**, không loại bỏ các hiệu ứng phụ đó. |

Không có một giá trị luôn đúng cho mọi framework. Hãy dựa vào **hợp đồng sử dụng lớp**: liệu caller cần lớp đã sẵn sàng ngay khi nhận `Lookup` hay runtime muốn kiểm soát lúc chạy mã khởi tạo?

**Đặc biệt:** `initialize=false` không giúp “bỏ qua” một lỗi trong `<clinit>`. Nó chỉ khiến lỗi có khả năng lộ ra **muộn hơn**, vào lúc lớp thực sự được khởi tạo. Do đó, khi dùng `false` để trì hoãn, hãy có điểm khởi tạo/kiểm thử có kiểm soát để lỗi xuất hiện ở nơi dễ quan sát.

## 7. Nếu `<clinit>` thất bại thì sao?

Initialization của lớp là quy trình do JVM quản lý và có thể thất bại nếu mã `static` ném exception hoặc xảy ra lỗi khác. Những trường hợp đáng nhớ:

1. Khi `initialize=true`, lỗi từ `<clinit>` có thể bộc lộ **ngay trong `defineHiddenClass`**.
2. Khi `initialize=false`, `defineHiddenClass` có thể trả bình thường, rồi lỗi chỉ xuất hiện ở **lần đầu invoke `static`** hoặc `ensureInitialized`.
3. Một exception không phải `Error` phát sinh trong khởi tạo thường được JVM bọc trong `ExceptionInInitializerError`. Các trường hợp JVM ném `Error` sẵn có có thể được truyền đi theo quy định.
4. Một class đã rơi vào **trạng thái khởi tạo lỗi** không được khởi tạo lại bình thường bằng cách chỉ gọi `ensureInitialized` lần nữa; các lần sử dụng sau có thể nhận `NoClassDefFoundError`.
5. Nếu tạo **lớp ẩn mới** từ cùng mảng bytecode, đó là **danh tính lớp mới** có quy trình khởi tạo độc lập, nhưng đừng xem việc định nghĩa lại là cơ chế phục hồi mặc định cho lỗi nghiệp vụ.

Hãy phân biệt **lỗi định nghĩa/liên kết** (ví dụ bytecode không hợp lệ, phiên bản class file không hỗ trợ, thiếu full privilege, tên package không phù hợp) với **lỗi khởi tạo** (mã `static` chạy rồi thất bại). `initialize=false` **không** cho phép bỏ qua kiểm tra và liên kết bytecode mà `defineHiddenClass` phải thực hiện.

Nếu mục tiêu là hệ thống nạp mã động an toàn, không nên tùy ý chạy mã `<clinit>` có hiệu ứng không kiểm soát. Chỉ tạo hidden class từ bytecode tin cậy và kiểm soát quyền, đầu vào, lỗi và thời điểm gọi.

## 8. Kiểm tra và gỡ lỗi thời điểm khởi tạo

Để xác định tại sao lớp ẩn chạy khối `static` sớm hoặc muộn hơn kỳ vọng:

1. **Đặt log trong một khởi tạo `static` thực sự** như `static int value = compute()`; không chỉ log trong constructor vì constructor thuộc giai đoạn tạo **đối tượng**, khác với khởi tạo **lớp**.
2. **Đặt log trước và sau `defineHiddenClass`.** Nếu `true`, log của `<clinit>` nằm trước log sau lời gọi. Nếu `false`, log của lớp ẩn chưa phải xuất hiện ở thời điểm này.
3. **Đặt log trước và sau `findStatic`, `invokeExact`, `ensureInitialized`.** Quan sát vị trí xuất hiện của `<clinit>` để tách bước tạo handle và bước gọi handle.
4. **Kiểm tra số lần tạo lớp ẩn.** Mỗi lời gọi `defineHiddenClass` có thể tạo class riêng; nếu nhận thấy log khởi tạo lặp nhiều lần, kiểm tra có đang tạo nhiều lớp từ cùng bytecode hay không.
5. **Kiểm tra lỗi và stack trace**: `ExceptionInInitializerError` hoặc `NoClassDefFoundError` có thể chỉ ra sự cố trước đó. Không nuốt exception rồi xem như lớp đã sẵn sàng.
6. **Dùng cấu hình runtime phù hợp**: thử với JDK thực tế dùng ở production và bật các cơ chế logging/tracing của JVM phù hợp khi cần. Không suy ra tính năng đang ở preview chỉ vì đây là lớp ẩn; API `defineHiddenClass` đã là chuẩn từ Java 15.

### Hai nhầm lẫn dễ mắc

**Nhầm 1: “`initialize=false` chỉ tạo đối tượng `Class` nên bytecode chưa được link.”** Sai. `defineHiddenClass` định nghĩa và liên kết hidden class trong cả hai trường hợp; `false` chỉ không yêu cầu khởi tạo.

**Nhầm 2: “Lấy `MethodHandle` là chạy `static` ngay.”** Không đúng với `findStatic` trong ví dụ. `findStatic` tạo handle, nhưng **gọi** handle tới phương thức `static` mới yêu cầu JVM khởi tạo class đó nếu chưa khởi tạo.

## 9. Tự kiểm tra

**Câu 1.** Một hidden class được tạo bằng `defineHiddenClass(bytes, false)`. Chỉ gọi `lookupClass()` và `isHidden()` thì có bắt buộc `<clinit>` chạy không?

**Đáp án:** Không. Đây là các thao tác lấy/kiểm tra metadata class. Tham số `false` chưa yêu cầu khởi tạo; một thao tác thực sự cần khởi tạo sẽ kích hoạt sau.

**Câu 2.** Cùng bytecode, gọi `defineHiddenClass(bytes, true)` ba lần. `<clinit>` chạy tối đa mấy lần?

**Đáp án:** Nếu cả ba lớp được khởi tạo thành công và có mã `<clinit>`, mỗi lời gọi tạo **một class ẩn khác nhau**, nên `<clinit>` chạy **một lần cho mỗi class**: ba lần. Không có cơ chế “một lần duy nhất cho cả mảng bytecode”.

**Câu 3.** `initialize=false` rồi `findStatic(...)` nhưng chưa invoke. Có thể kết luận `static` đã chạy?

**Đáp án:** Không. Việc tạo handle không đồng nghĩa thực thi method. Trong ví dụ thực nghiệm, `<clinit>` chỉ chạy trước lần `getter.invokeExact()` đầu tiên.

**Câu 4.** Muốn định nghĩa trước và chủ động khởi tạo sau mà không gọi phương thức nghiệp vụ, API chuẩn nào?

**Đáp án:** `Lookup.ensureInitialized(hiddenClass)` từ `Lookup` có quyền phù hợp.

**Câu 5.** Nếu `initialize=false`, mã `static` lỗi có biến mất không?

**Đáp án:** Không. Lỗi bị **trì hoãn** tới lúc JVM thực hiện khởi tạo. Nếu khởi tạo thất bại, class có thể ở trạng thái lỗi theo quy tắc JVM.

## Ghi nhớ

- **`defineHiddenClass(bytes, true)`:** định nghĩa, liên kết **và khởi tạo** lớp ẩn trước khi trả kết quả bình thường.
- **`defineHiddenClass(bytes, false)`:** định nghĩa và liên kết trước; **không chủ động chạy `<clinit>` ngay**, để các thao tác sau kích hoạt.
- **`findStatic` tạo handle; `invokeExact` của handle tới phương thức `static` kích hoạt khởi tạo** nếu lớp chưa được khởi tạo.
- **`ensureInitialized` cho phép chủ động kiểm soát thời điểm khởi tạo** sau khi đã định nghĩa.
- **Một lần khởi tạo thành công cho mỗi danh tính class**; tạo nhiều lớp ẩn từ cùng bytecode không dùng chung trạng thái `static`.
- Tham số `initialize` chỉ điều khiển **thời điểm khởi tạo**, không thay đổi quyền `Lookup`, cơ chế linking, điều kiện bytecode hợp lệ hay chính sách unload.

### Tài liệu tham khảo còn áp dụng

- [Oracle Java 25 – MethodHandles.Lookup, defineHiddenClass](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html#defineHiddenClass(byte%5B%5D,boolean,java.lang.invoke.MethodHandles.Lookup.ClassOption...)): định nghĩa, liên kết, initialize và hidden class identity.
- [Oracle Java 25 – Lookup.ensureInitialized](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html#ensureInitialized(java.lang.Class)): ép khởi tạo có kiểm soát.
- [Java Language Specification `12.4 – Initialization](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.4): điều kiện kích hoạt và quy trình khởi tạo class.
- [Java Virtual Machine Specification `5.5 – Initialization](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.5): quy tắc khởi tạo ở mức JVM.
- [OpenJDK JEP 371 – Hidden Classes](https://openjdk.org/jeps/371): mục đích và thiết kế hidden classes đưa vào Java 15.
