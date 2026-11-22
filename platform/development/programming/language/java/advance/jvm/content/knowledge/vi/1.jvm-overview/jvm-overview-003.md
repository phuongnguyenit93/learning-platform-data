# Đường đi của chương trình Java: mã nguồn → javac → .class → JVM → mã máy

Khi viết một chương trình Java, CPU **không trực tiếp chạy tệp `.java`**. Với quy trình thông thường, trình biên dịch `javac` chuyển mã nguồn thành **Java bytecode** trong tệp `.class`; khi khởi chạy, JVM nạp và kiểm tra các lớp, rồi thực thi bytecode bằng bộ thông dịch và/hoặc biên dịch JIT thành **lệnh máy của CPU đang dùng**. Đây là lý do cùng một tệp `.class` có thể chạy trên những hệ điều hành và bộ xử lý khác nhau, miễn là có JVM tương thích và các phụ thuộc phù hợp.

```text
Hello.java (mã nguồn Java)
       │ javac: phân tích + kiểm tra kiểu + sinh bytecode
       ▼
Hello.class (bytecode JVM, chưa phải mã máy x86/ARM)
       │ java: khởi động JVM và tìm lớp main
       ▼
JVM: Class Loading → Verification/Linking → Initialization khi cần
       │
       ├── Interpreter: đọc và thực thi từng lệnh bytecode
       └── JIT: biên dịch mã được chọn thành mã máy, có thể tối ưu
                    │
                    ▼
       Mã máy + thư viện/runtime của JVM
                    │
                    ▼
           Hệ điều hành / CPU thực thi
```

Sơ đồ là **mô hình tư duy**, không có nghĩa mọi lớp đều được nạp ngay lúc khởi động, mọi bytecode luôn được thông dịch trước khi JIT, hoặc mọi phương thức đều được JIT biên dịch. Chiến lược cụ thể tùy phiên bản và bản triển khai JVM.

## 1. Phân biệt mã nguồn, bytecode và mã máy

| Tầng | Dạng biểu diễn | Ai xử lý? | Ý nghĩa |
| --- | --- | --- | --- |
| Mã nguồn | `.java`, cú pháp Java con người đọc được | `javac` hoặc công cụ biên dịch khác | Định nghĩa lớp, phương thức và quy tắc chương trình |
| Bytecode | `.class` theo định dạng JVM Class File | JVM (class loader, verifier, interpreter/JIT) | Tập lệnh trừu tượng, gần như độc lập kiến trúc CPU |
| Mã máy | Lệnh native phù hợp x86-64, AArch64, ... | CPU, với sự hỗ trợ của hệ điều hành/runtime | Lệnh thực sự được bộ xử lý thực thi |

- `.class` **không phải** bản dịch máy cuối cùng cho một hệ điều hành/CPU. Một tệp class chứa constant pool, metadata lớp/phương thức/trường và các phần `Code` bytecode cho những phương thức có mã; phương thức `abstract` hoặc `native` không có phần bytecode như phương thức Java thông thường.
- JVM được xây dựng riêng cho nền tảng đích và bản thân JVM là chương trình native. Ngay cả khi chạy bytecode bằng interpreter, CPU vẫn đang chạy **mã máy của interpreter** để diễn giải các lệnh bytecode.
- Khả năng “write once, run anywhere” phụ thuộc vào **phiên bản class file, API/runtime sẵn có, thư viện bên ngoài và hành vi phụ thuộc nền tảng**. Mã dùng native library hoặc giả định đường dẫn/tính năng hệ điều hành vẫn có thể không portable.

### JDK, JVM và lệnh `java`

**JDK** (Java Development Kit) cung cấp bộ công cụ phát triển như `javac`, `java`, `javap`, công cụ đóng gói và một runtime Java. **JVM** là máy ảo thực thi class file; runtime còn có các thư viện chuẩn Java. `javac` và `java` là **hai công cụ khác vai trò**: `javac` tạo bytecode, còn trình khởi chạy `java` thiết lập runtime/JVM và thực thi chương trình.

```bash
javac --version
java --version
```

Hai lệnh nên cùng một môi trường JDK dự định sử dụng. Nếu thiết lập `PATH` trỏ tới hai bản khác nhau, có thể xuất hiện lỗi tương thích dù mã nguồn đã biên dịch thành công.

## 2. Ví dụ chạy được: đi từ `.java` tới `.class`

Tạo tệp **`Hello.java`** (tên tệp phải khớp với tên `public class Hello`):

```java
public class Hello {
    public static void main(String[] args) {
        int left = 20;
        int right = 22;
        int sum = left + right;
        System.out.println("Kết quả: " + sum);
    }
}
```

Trong terminal có JDK 17 trở lên, đứng tại thư mục chứa `Hello.java`:

```bash
mkdir out
javac -encoding UTF-8 -d out Hello.java
java -cp out Hello
```

Kết quả chuẩn:

```text
Kết quả: 42
```

Giải thích từng phần:

1. `mkdir out` tạo thư mục đặt sản phẩm biên dịch; tùy hệ điều hành/lệnh shell có thể dùng cách tạo thư mục tương đương.
2. `javac -encoding UTF-8 -d out Hello.java` đọc mã nguồn, phân tích cú pháp, kiểm tra các quy tắc ngôn ngữ/kiểu và tạo **`out/Hello.class`**. Tùy mã nguồn, có thể sinh thêm class file cho các lớp khác; ví dụ này chỉ cần `Hello.class`.
3. `java -cp out Hello` đặt `out` lên classpath, tìm tên lớp **`Hello`**, khởi động runtime và gọi phương thức `public static void main(String[] args)`. Tham số `Hello` là **tên lớp**, không phải `Hello.class` hay đường dẫn đến tệp `.java`.
4. JVM và các thư viện chuẩn thực thi `main`; `System.out.println` ghi dòng kết quả ra standard output. Việc in ra màn hình cuối cùng đi qua các chức năng của runtime/hệ điều hành.

Nếu khai báo `package com.example;`, tệp thường đặt tương ứng với package, sản phẩm nằm tại `out/com/example/Hello.class` và lệnh chạy là `java -cp out com.example.Hello`. Đây là **fully qualified class name**; thư mục classpath là **gốc của cây package**, không phải thư mục chứa `Hello.class` sau cùng.

### Nhìn vào bytecode thật bằng `javap`

```bash
javap -classpath out -c Hello
```

Công cụ `javap` phân rã thông tin class file và hiển thị bytecode. Trong phương thức `main`, ví dụ này thường có các thao tác tương đương: đưa số nguyên lên operand stack, lưu/đọc local variables, dùng **`iadd`** để cộng, lấy `System.out` và gọi `println`. Java 17 có thể biểu diễn phép nối chuỗi qua **`invokedynamic`**. Số offset, constant-pool index và cách biên dịch từng biểu thức là **chi tiết đầu ra của compiler**: hãy xem dữ liệu thật từ `javap`, không thuộc lòng một listing giả định.

`javap -c` cho thấy **bytecode**, không chứng minh lệnh máy JIT sẽ có hình dạng nào; JIT được phép tối ưu hoặc loại bỏ những thao tác trung gian miễn là giữ ngữ nghĩa cần thiết.

## 3. `javac` làm gì ở thời điểm biên dịch?

Nói đơn giản, trình biên dịch thực hiện chuỗi công việc sau:

1. **Đọc và phân tích cú pháp:** biến chuỗi ký tự/tokens thành cấu trúc chương trình, kiểm tra cú pháp hợp lệ.
2. **Phân giải tên và kiểm tra ngữ nghĩa/kiểu:** xác định lớp, biến, overload, quyền truy cập, kiểu trả về, phép gán và các luật ngôn ngữ. Nếu sai, `javac` báo lỗi và không tạo bản class file hợp lệ cho phần bị lỗi.
3. **Biến đổi các cấu trúc mức cao:** nhiều tính năng Java như vòng `for-each`, generic (type erasure), lambda hoặc nối chuỗi được biểu diễn lại bằng bytecode và metadata phù hợp. Một số tính năng có thể sử dụng `invokedynamic` thay vì mô phỏng mọi thứ bằng chuỗi lệnh đơn giản.
4. **Sinh class file:** xuất constant pool, descriptor, bytecode và thuộc tính cần cho runtime. File format có **major version** để JVM biết class file có tương thích hay không.

Ví dụ, `javac` phát hiện được lỗi kiểu như gán `String` cho `int` nhưng không dự đoán được mọi lỗi khi chương trình chạy: chia cho 0, truy cập phần tử ngoài mảng, lỗi mạng hay thiếu một lớp ở runtime có thể chỉ lộ ra sau đó.

**Lưu ý:** kiểm tra của `javac` và **bytecode verification của JVM** là hai bước khác nhau. `javac` xác minh chương trình nguồn, còn JVM kiểm tra tính hợp lệ/an toàn cấu trúc bytecode khi nạp/liên kết lớp, kể cả class file không được tạo bởi `javac`.

## 4. Khi chạy `java -cp out Hello`, JVM làm gì?

### 4.1. Khởi động và nạp lớp (loading)

Trình `java` xác định cách khởi chạy (lớp main, JAR, module hoặc source-file mode), cấu hình JVM, classpath/module path và các tham số. JVM khởi tạo runtime thiết yếu và sử dụng hệ thống class loader để tìm định nghĩa lớp khi cần.

- **Bootstrap class loader** chịu trách nhiệm cho các lớp nền tảng cốt lõi.
- **Platform class loader** và **application/system class loader** phục vụ các nhóm lớp nền tảng khác và lớp ứng dụng, tùy cấu hình/module.
- Việc ủy quyền class loading thường giúp ưu tiên định nghĩa được phép ở loader cha; có thể có custom class loader cho plugin, container hoặc framework.

Loading đưa **định nghĩa lớp** từ class file hoặc nguồn khác vào runtime. Chỉ đặt tệp `.class` trên đĩa chưa có nghĩa JVM đã nạp nó. Nạp/lazy linking có thể xảy ra trong lúc chương trình đang chạy.

### 4.2. Linking: verification, preparation, resolution

Theo mô hình vòng đời lớp trong JVM:

- **Verification:** kiểm tra class file/bytecode có tuân thủ các ràng buộc cấu trúc và kiểu cần thiết; lỗi có thể dẫn đến `VerifyError`.
- **Preparation:** cấp phát và gán **giá trị mặc định** cho các static fields của lớp (chẳng hạn `0` cho `int`, `null` cho reference). Đây chưa phải lúc thực thi tất cả câu lệnh khởi tạo static trong mã Java.
- **Resolution:** biến các symbolic reference trong constant pool thành tham chiếu runtime cụ thể khi cần; việc resolution có thể được thực hiện muộn, không bắt buộc xử lý toàn bộ ngay trước `main`.

Các khái niệm loading/linking/initialization khác nhau; đừng gộp tất cả thành “JVM đọc class rồi chạy luôn”.

### 4.3. Initialization và lời gọi `main`

Khi một lớp được sử dụng chủ động trong những trường hợp luật JVM quy định, JVM thực hiện **class initialization**: các static field initializers và `static { ... }` chạy theo thứ tự tương ứng trong lớp, thông qua phương thức khởi tạo lớp ở mức bytecode (`<clinit>`, khi có). Chỉ sau các điều kiện khởi tạo cần thiết, runtime mới thực thi phần chương trình liên quan.

Trong ví dụ `Hello`, entry point là `main(String[] args)`. JVM thiết lập luồng thực thi và các stack frames để chạy phương thức; có thể gọi tiếp các phương thức trong thư viện chuẩn và mã của ứng dụng.

## 5. Từ bytecode đến lệnh máy: interpreter và JIT

Bytecode bao gồm các lệnh như `iload`, `istore`, `iadd`, `invokevirtual`, `return`. Chúng vận hành trên **mô hình stack** của JVM (operand stack, local variables, frame), không phải trực tiếp là lệnh thanh ghi của một CPU cụ thể.

**Interpreter:** runtime có thể đọc lần lượt lệnh bytecode của một phương thức và thực hiện hành vi tương ứng. Đây là cách có thể bắt đầu thực thi mã nhanh mà chưa cần biên dịch native riêng cho phương thức ấy, đổi lại một số chi phí diễn giải lệnh.

**JIT (Just-In-Time compiler):** khi runtime nhận thấy những đoạn mã có lợi để tối ưu, JIT có thể chuyển bytecode sang **mã máy cho CPU hiện tại**, lưu trong bộ nhớ mã và tái sử dụng cho các lần thực thi sau. HotSpot thường dùng cơ chế **tiered compilation** kết hợp thu thập thông tin thực thi với các trình biên dịch như C1/C2; đây là chi tiết của một JVM phổ biến, **không phải cam kết chung của mọi JVM**.

Ví dụ cơ chế có thể diễn ra:

```text
main() gọi calculate() nhiều lần
        │
        ├── Ban đầu: interpreter và/hoặc tầng mã nhanh
        ├── JVM quan sát số lần gọi, nhánh hay gặp, kiểu đối tượng thực tế
        ├── JIT tạo mã máy tối ưu cho calculate()
        └── Những lần gọi tiếp theo có thể chạy mã máy đã biên dịch
```

JIT có thể **inline** lời gọi, tối ưu vòng lặp, bỏ kiểm tra dư thừa khi chứng minh được an toàn, và tận dụng profiling. Nếu một giả định tối ưu không còn đúng, runtime có thể **deoptimize** để quay về trạng thái thực thi phù hợp. Không được suy ra rằng “phương thức chạy lần đầu = interpreter, lần thứ hai = JIT”; ngưỡng và chiến lược phụ thuộc JVM, tùy chọn và đặc điểm chương trình.

CPU cuối cùng chạy cả mã native của JVM/interpreter, mã do JIT sinh (nếu có), mã runtime và thư viện native. **Mã máy không được ghi thành tệp `.exe` chỉ vì chạy `java Hello`**; JIT thường biên dịch tại runtime trong bộ nhớ tiến trình. Các cơ chế AOT/native image là con đường khác, nằm ngoài luồng `javac → .class → JVM` cơ bản.

### Bytecode portable, hiệu năng vẫn phụ thuộc môi trường

Cùng bytecode có thể được các JVM khác nhau chạy trên x86-64 hoặc ARM64; runtime chọn cơ chế thực thi tương thích với CPU. Nhưng hiệu năng phụ thuộc JIT, bộ nhớ/GC, profile tải, môi trường hệ điều hành và tài nguyên. Kết luận rằng “Java luôn chậm vì phải thông dịch” là không đúng với các runtime có JIT; kết luận “Java luôn nhanh như native” cũng không thể khái quát.

## 6. Các vùng dữ liệu xuất hiện trong lúc thực thi

Dù bài học tập trung vào đường đi biên dịch, cần phân biệt một số nơi runtime sử dụng:

| Khái niệm | Vai trò trong lúc chương trình chạy |
| --- | --- |
| **Heap** | Chứa các đối tượng/mảng được cấp phát; garbage collector quản lý thu hồi bộ nhớ phù hợp |
| **JVM stack của từng thread** | Chứa stack frames cho các lời gọi phương thức Java; frame có local variables, operand stack và thông tin liên kết |
| **Method area / metadata lớp** | Lưu cấu trúc runtime liên quan đến lớp, phương thức và constant pool; HotSpot thường dùng **Metaspace** cho nhiều metadata lớp |
| **PC register của từng thread** | Theo dõi vị trí lệnh JVM liên quan đến luồng thực thi hiện tại |
| **Native method stack / bộ nhớ native** | Hỗ trợ mã native và runtime; chi tiết phụ thuộc JVM và nền tảng |
| **Code cache (ở HotSpot)** | Chứa mã máy do JIT biên dịch và một số mã được runtime tạo |

`javac` tạo **class file** trên đĩa; JVM sau đó tạo nhiều cấu trúc **trong bộ nhớ** để nạp lớp và chạy. Đừng nhầm **`Hello.class` trên đĩa**, **metadata lớp trong runtime** và **đối tượng `new Hello()` trên heap** thành cùng một thứ.

## 7. Phiên bản Java quyết định khả năng chạy class file

JVM cần hỗ trợ **class-file major version** của bytecode được nạp. Ví dụ phổ biến:

| Mục tiêu biên dịch | Class-file major version |
| --- | ---: |
| Java 17 | 61 |
| Java 21 | 65 |

Chạy class file được tạo với target Java 21 trên runtime chỉ hỗ trợ Java 17 sẽ phát sinh `UnsupportedClassVersionError`. Trên JDK 21, có thể biên dịch cho Java 17 bằng:

```bash
javac --release 17 -encoding UTF-8 -d out Hello.java
```

`--release 17` chọn ngữ nghĩa ngôn ngữ, định dạng class file và API nền tảng tương ứng với release đích (trong khả năng công cụ hỗ trợ). **Không đảm bảo** các thư viện ngoài hoặc native dependencies chạy được chỉ nhờ thay `--release`. Ngược lại, bytecode target 17 thường có thể chạy trên JVM mới hơn nếu không có bất tương thích từ thư viện/cấu hình.

Có thể xem major version bằng:

```bash
javap -classpath out -verbose Hello
```

Tìm dòng `major version` trong kết quả. Không cần mở tệp nhị phân bằng trình soạn thảo văn bản.

## 8. Các cách khởi chạy và nơi chứa bytecode

- **Lớp trên classpath:** `java -cp out Hello` tải `Hello` qua classpath; với package, dùng tên đầy đủ của lớp.
- **JAR:** `jar --create --file app.jar --main-class Hello -C out .` đóng gói các class; `java -jar app.jar` chạy entry point từ manifest. JAR là tệp lưu trữ chứa bytecode/tài nguyên, bản thân JAR không phải mã máy.
- **Module:** ứng dụng Java module dùng module path và `java --module-path ... -m module.name/com.example.Main` theo cấu trúc module; nó thay đổi cách tổ chức/resolve module, không thay bản chất bytecode → JVM.
- **Source-file mode (JDK 11+):** `java Hello.java` có thể biên dịch và chạy tệp nguồn ở một lệnh. Nó vẫn dùng compiler/runtime bên dưới; đừng hiểu nhầm rằng CPU trực tiếp chạy cú pháp `.java`.

Với ví dụ `Hello.java`, quy trình tách `javac` rồi `java` vẫn hữu ích nhất để quan sát được **tệp class trung gian**.

## 9. Cách xác định lỗi xảy ra ở tầng nào

| Triệu chứng | Giai đoạn cần kiểm tra | Hướng kiểm tra |
| --- | --- | --- |
| `javac` báo `';' expected`, `cannot find symbol`, `incompatible types` | Biên dịch nguồn | Cú pháp, import, kiểu và dependency của compiler |
| `Could not find or load main class Hello` | Launch / class loading | Tên lớp, package, vị trí `Hello.class`, `-cp out` |
| `UnsupportedClassVersionError` | Nạp class trên JVM | So sánh `java --version`, `javap -verbose`, cấu hình `--release` |
| `NoClassDefFoundError` | Liên kết/nạp hoặc sử dụng lớp tại runtime | Dependency runtime, classpath/module path, lỗi khởi tạo trước đó; đọc nguyên nhân kèm theo |
| `VerifyError` | Bytecode verification | Class file không hợp lệ, bytecode tool/instrumentation hoặc xung đột phiên bản |
| `ExceptionInInitializerError` | Class initialization | Static initializer hoặc static field initialization ném exception |
| `NullPointerException`, `ArithmeticException` | Thực thi | Logic và giá trị runtime; biên dịch thành công không loại bỏ lỗi này |

Không gán mọi lỗi “không chạy được” cho JVM. Ví dụ `cannot find symbol` của `javac` là lỗi **compile-time**; lỗi thiếu lớp khi `java` nạp dependency là vấn đề **runtime**. Khi có lỗi, hãy giữ nguyên **stack trace** và kiểm tra chính xác giai đoạn.

## 10. Tự kiểm chứng đường đi của một chương trình

Có thể thực hiện chuỗi thao tác theo thứ tự:

1. Chạy `javac --version` và `java --version` để biết compiler/runtime đang dùng.
2. Tạo `Hello.java`, chạy `javac -encoding UTF-8 -d out Hello.java` rồi xác nhận có tệp `out/Hello.class`.
3. Chạy `javap -classpath out -c Hello` để quan sát các lệnh bytecode, trong đó có hành vi cộng `20 + 22`.
4. Chạy `java -cp out Hello` và xác nhận chỉ có dòng `Kết quả: 42` từ chương trình ví dụ.
5. Thử đổi `int right = 22;` thành `int right = "22";`: lỗi xuất hiện ở **`javac`**, chương trình mới không biên dịch thành công.
6. Phục hồi tệp, biên dịch lại và thử chạy bằng tên lớp sai hoặc classpath sai: lúc này lỗi xuất hiện ở **bước `java` tìm/nạp lớp**.

### Câu hỏi tự kiểm tra

- `javac` có tạo lệnh máy x86-64 trực tiếp không? **Không**; thông thường nó tạo bytecode trong `.class`.
- Nếu JVM sử dụng interpreter, CPU có thực thi bytecode trực tiếp như mã native không? **Không**; CPU thực thi mã máy của interpreter.
- Tại sao có thể chạy cùng `.class` trên CPU khác? **JVM của từng nền tảng** hiểu cùng định dạng bytecode và tạo/thực thi hành vi thích hợp.
- JIT có bắt buộc biên dịch mọi phương thức không? **Không**; tùy JVM và hành vi chương trình.
- Java biên dịch thành công có đồng nghĩa mọi lỗi đã bị loại bỏ không? **Không**; class loading, initialization và logic runtime vẫn có thể lỗi.

Khi nhìn vào toàn bộ đường đi, hãy phân biệt chính xác **`javac` biến mã nguồn thành bytecode**, **JVM xác minh/nạp/khởi tạo lớp**, và **runtime diễn giải hoặc JIT biên dịch bytecode để CPU có thể thực thi các lệnh native**. Các lớp trung gian giải thích đồng thời khả năng portable, cơ chế tối ưu runtime và nguồn gốc của từng nhóm lỗi.