# Mối liên hệ giữa mã nguồn, trình biên dịch, bytecode và JVM

## 1. Bức tranh tổng thể

Khi viết Java, bạn tạo **mã nguồn** (thường là tệp `.java`) để con người đọc và chỉnh sửa. Công cụ **`javac`** trong JDK biên dịch mã nguồn thành **bytecode** ở tệp `.class`. Khi chạy, chương trình **`java`** khởi động JVM, JVM tải những class cần thiết, kiểm tra và liên kết chúng, rồi thực thi bytecode bằng cơ chế thông dịch hoặc biên dịch JIT tùy JVM và quá trình chạy.

Mục tiêu của bài này là trả lời chính xác bốn câu hỏi:

1. `.java` và `.class` chứa những gì, chúng khác nhau ra sao?
2. `javac` làm việc lúc **biên dịch**, còn `java` và JVM làm việc lúc **chạy** như thế nào?
3. Vì sao bytecode Java thường dùng được trên nhiều hệ điều hành, và giới hạn của điều đó là gì?
4. Làm sao tự biên dịch, chạy, xem bytecode và chẩn đoán lỗi ở từng giai đoạn?

~~~mermaid
flowchart LR
    SRC["HelloPipeline.java<br/>Mã nguồn Java"] -->|"javac"| CLS["HelloPipeline.class<br/>Bytecode"]
    CLS -->|"java: khởi động JVM"| JVM["JVM<br/>Nạp, xác minh, liên kết,<br/>khởi tạo và thực thi class"]
    JVM -->|"Thông dịch hoặc JIT<br/>khi thích hợp"| NATIVE["Lệnh máy chạy trên<br/>CPU và hệ điều hành"]
~~~

Sơ đồ mô tả luồng phổ biến khi **biên dịch trước rồi chạy**. Nó không có nghĩa mọi bytecode đều được JIT biên dịch, cũng không có nghĩa JVM luôn nạp tất cả class của ứng dụng ngay khi khởi động.

## 2. Phân biệt bốn thành phần

| Thành phần | Vai trò | Thời điểm và kết quả |
|---|---|---|
| **Mã nguồn Java** | Biểu diễn lớp, phương thức, câu lệnh theo cú pháp Java | Người học tạo `HelloPipeline.java` |
| **Trình biên dịch `javac`** | Kiểm tra cú pháp, tên, kiểu và nhiều ràng buộc tĩnh; tạo bytecode | `javac HelloPipeline.java` tạo `HelloPipeline.class` nếu thành công |
| **Bytecode / tệp `.class`** | Chứa biểu diễn class đã biên dịch: metadata, constant pool, phương thức và chỉ thị bytecode | Là đầu vào cho JVM; **không phải** mã máy trực tiếp của Windows/Linux |
| **JVM** | Môi trường thực thi Java bytecode; quản lý tải class, bộ nhớ, exception và runtime | Một JVM thích hợp thực hiện lời gọi `main` cùng các class được sử dụng |

**JDK** (Java Development Kit) cung cấp các công cụ phát triển, tiêu biểu là `javac`, `java`, `javap`, cùng runtime Java. **JVM** là máy ảo thực thi bytecode, không phải tên khác của trình biên dịch. Trong cách phân phối Java hiện đại, thường cài **JDK** để vừa biên dịch vừa chạy; tài liệu cũ có thể gọi phần runtime riêng là **JRE**.

Phân biệt thêm: chương trình `java` là **launcher** (lệnh khởi động runtime); JVM là môi trường thực thi mà launcher khởi tạo. Nói ngắn gọn “chạy bằng Java” thường chỉ cả quá trình này, nhưng khi chẩn đoán lỗi, nên biết bước nào đã thất bại.

## 3. Ví dụ Java có thể tự chạy

Tạo tệp **`HelloPipeline.java`** (đúng chữ hoa/thường của public class) với nội dung:

~~~java
public class HelloPipeline {
    private static int twice(int value) {
        return value * 2;
    }

    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : args[0];

        System.out.println("Xin chao, " + name);
        System.out.println("2 * 3 = " + twice(3));
    }
}
~~~

Giả sử đã cài **JDK 17 hoặc mới hơn**. Mở terminal trong thư mục chứa tệp. Kiểm tra:

~~~bash
java -version
javac -version
~~~

Biên dịch và chạy (ví dụ cố định đích bytecode Java 17):

~~~bash
javac --release 17 -encoding UTF-8 HelloPipeline.java
java -cp . HelloPipeline
~~~

Kết quả dự kiến:

~~~text
Xin chao, Java
2 * 3 = 6
~~~

Thử truyền một đối số từ dòng lệnh:

~~~bash
java -cp . HelloPipeline Linh
~~~

Kết quả:

~~~text
Xin chao, Linh
2 * 3 = 6
~~~

Giải thích chính xác:

- `javac` đọc nội dung tệp nguồn, kiểm tra mã rồi tạo `HelloPipeline.class` trong thư mục hiện hành. Nếu biên dịch báo lỗi, bạn cần sửa source và biên dịch lại.
- `java -cp . HelloPipeline` yêu cầu launcher tìm **class tên `HelloPipeline` trên classpath** (dấu `.` là thư mục hiện hành), sau đó JVM thực hiện phương thức `public static void main(String[] args)` của class ấy.
- Khi chạy class đã biên dịch, tham số cho `java` là **tên class**, không phải tên tệp `.class`. Đúng: `java HelloPipeline`; sai trong chế độ này: `java HelloPipeline.class`.
- `args` chứa các đối số **sau** tên class. Trường hợp không có đối số đã được bảo vệ bằng `args.length == 0`, vì truy cập thẳng `args[0]` khi mảng trống sẽ gây `ArrayIndexOutOfBoundsException`.

**Lưu ý về `-encoding UTF-8`:** cờ này hướng dẫn `javac` đọc mã nguồn bằng UTF-8; nó **không tự thay đổi encoding của terminal**. Nếu chuỗi có dấu tiếng Việt in ra sai trên một số console, cần kiểm tra encoding của console và môi trường chạy riêng.

## 4. `javac` kiểm tra và tạo bytecode như thế nào?

Xét đoạn mã trong ví dụ:

~~~java
private static int twice(int value) {
    return value * 2;
}
~~~

Ở mức ý tưởng, trình biên dịch phải xác minh rằng:

1. Cú pháp khai báo lớp, phương thức và câu lệnh hợp lệ.
2. Biến `value` được khai báo, có kiểu `int` và phép nhân `value * 2` hợp lệ.
3. Giá trị trả về phù hợp với kiểu khai báo `int`.
4. Lời gọi `twice(3)` từ `main` có thể được giải quyết tới phương thức tương ứng.

Nếu viết `return "sai kiểu";`, `javac` sẽ từ chối bởi phương thức khai báo trả `int` nhưng biểu thức trả `String`. Lỗi này xảy ra **trước khi chương trình được chạy**.

Sau khi kiểm tra thành công, trình biên dịch tạo tệp `.class`. Một tệp class có thể chứa thông tin như tên class và superclass, các field/method, mô tả kiểu, constant pool và phần mã bytecode của method. Mức chi tiết phụ thuộc compiler, phiên bản Java và các tùy chọn biên dịch.

**Không nên đồng nhất việc “biên dịch thành công” với “chương trình đúng”.** `javac` không tự chứng minh mọi quy tắc nghiệp vụ, không chạy thử mọi nhánh, và thường không phát hiện lỗi như chia cho 0 ở một đường thực thi runtime, file không tồn tại hay `NullPointerException` phát sinh bởi dữ liệu thực.

## 5. Tự xem bytecode thay vì chỉ tưởng tượng

JDK có công cụ **`javap`** để xem cấu trúc một tệp `.class`. Sau khi biên dịch thành công, chạy:

~~~bash
javap -c -p HelloPipeline
~~~

Các phần có thể quan sát:

- Phương thức `twice(int)`, `main(java.lang.String[])` và constructor mặc định.
- Các chỉ thị thực hiện phép toán và lời gọi phương thức, chẳng hạn `iload`, `imul`, `ireturn` ở `twice`.
- Các thao tác truy cập `System.out` và gọi `println` trong `main`.
- Với phép nối chuỗi trên các JDK hiện đại, compiler có thể dùng `invokedynamic` thay vì một chuỗi lệnh nối `StringBuilder` dễ đoán.

Muốn xem metadata/class file version:

~~~bash
javap -verbose HelloPipeline
~~~

Nếu đã biên dịch bằng `--release 17`, phần class file thường hiển thị **`major version: 61`**. Đây là định dạng class file Java 17, không phải phiên bản hệ điều hành và cũng không phải số phiên bản của mã nguồn.

`javap` là công cụ **disassembler/inspector**: nó trình bày bytecode và metadata theo dạng người đọc được, không chạy ứng dụng. Không cần thuộc lòng từng opcode; hãy nhận ra **bytecode là lớp biểu diễn trung gian**, khác mã nguồn và khác mã máy của CPU.

### Kiểm chứng bằng một thay đổi có chủ đích

Đổi `return value * 2;` thành `return value * 3;`, **lưu tệp rồi chỉ chạy lại `java HelloPipeline` mà không biên dịch lại**. Kết quả vẫn đến từ `.class` cũ: `2 * 3 = 6`. Khi chạy lại `javac --release 17 -encoding UTF-8 HelloPipeline.java`, kết quả mới thành `2 * 3 = 9`. **Chú ý:** chuỗi nhãn `2 * 3 = ` trong `println` vẫn giữ nguyên, nhưng phép tính bên trong đã đổi thành nhân 3. Vì vậy, nhãn lúc này không mô tả đúng phép toán thực tế; đây là một ví dụ nhỏ về **kết quả trình bày sai ý nghĩa dù mã hợp lệ**. Hãy đổi nhãn nếu muốn thông tin hiển thị chính xác.

Đây là cách thực nghiệm rất rõ để phân biệt **source hiện tại** với **bytecode mà JVM đang thực thi**. Sau bài tập, hãy khôi phục `twice` về phép nhân 2 để các ví dụ còn lại nhất quán.

## 6. JVM làm gì sau lệnh `java`?

Với chế độ chạy class đã biên dịch, tiến trình diễn ra gần đúng như sau:

1. **Khởi động runtime:** launcher `java` xử lý tùy chọn, classpath/module path và yêu cầu class chính.
2. **Class loading:** JVM dùng các class loader để tìm, đọc và định nghĩa những class cần thiết. Nhiều class chỉ được tải khi được sử dụng.
3. **Linking:** JVM xác minh tính hợp lệ của class file (*verification*), chuẩn bị các cấu trúc/static storage cần thiết (*preparation*) và giải quyết symbolic references (*resolution*). Một số bước có thể được thực hiện trễ khi cần theo quy tắc JVM.
4. **Initialization:** trước khi dùng một class theo các trường hợp kích hoạt khởi tạo, JVM thực hiện static field initializer/static block của class ấy theo quy tắc ngôn ngữ.
5. **Execution:** JVM gọi `main`, thực hiện bytecode của chương trình, tạo object, gọi method, xử lý exception và quản lý bộ nhớ trong runtime.

JVM triển khai phổ biến có thể **thông dịch** bytecode ban đầu và dùng **JIT compiler** để tối ưu/biên dịch một số đoạn chạy nhiều lần thành native machine code. Điều đó thường cải thiện tốc độ, nhưng không bảo đảm mọi method đều được JIT. Các JVM khác nhau có thể chọn chiến lược thực thi khác nhau mà vẫn hỗ trợ cùng mô hình Java.

**Garbage collection (GC)** là dịch vụ runtime liên quan đến quản lý bộ nhớ object. Nó không thuộc nhiệm vụ `javac`, cũng không biến bytecode thành native code; GC và JIT là hai cơ chế khác nhau.

## 7. Vì sao Java được nói là “viết một lần, chạy nhiều nơi”?

Cùng một tệp `.class` hợp lệ có thể chạy trên các hệ điều hành khác nhau **nếu** ở đó có JVM tương thích với phiên bản class file và các API mà chương trình sử dụng.

| Thành phần | Có phụ thuộc hệ điều hành/kiến trúc không? |
|---|---|
| `HelloPipeline.java` | Mã nguồn thường có thể chia sẻ; môi trường build vẫn có thể khác |
| `HelloPipeline.class` | Bytecode được chuẩn hóa và thường có thể chuyển nền tảng |
| Bản cài JVM/JDK | Có bản build theo OS và CPU (Windows x64, Linux ARM, …) |
| Native library qua JNI, công cụ hệ thống, đường dẫn file | Có thể phụ thuộc nền tảng và cần xử lý riêng |

Vì vậy **portable bytecode** không có nghĩa “chạy được trên mọi máy mà không cài gì”. Máy chạy cần runtime phù hợp; ứng dụng có thể phụ thuộc vào thư viện, quyền truy cập file, cấu hình, native component hoặc phiên bản Java cụ thể.

Ví dụ, tệp class tạo bằng JDK mới có thể dùng **class file version cao hơn** JVM cũ hỗ trợ. Trường hợp đó xảy ra lỗi `UnsupportedClassVersionError` khi JVM cố nạp class, dù mã Java của bạn không có lỗi cú pháp.

## 8. Phiên bản JDK, `--release` và khả năng tương thích

Khi phát triển trên JDK mới nhưng cần chạy trên Java 17, hãy biên dịch với:

~~~bash
javac --release 17 -encoding UTF-8 HelloPipeline.java
~~~

`--release 17` yêu cầu `javac` dùng quy tắc ngôn ngữ, class file target và tập public API tiêu chuẩn tương ứng với Java 17. Nó thường đáng tin cậy hơn việc chỉ đổi class-file target mà vẫn vô tình gọi API Java mới.

Điều kiện: **trình biên dịch phải hỗ trợ release được chọn**. Một JDK cũ hơn không thể biên dịch cho ngôn ngữ/release mới mà nó chưa biết.

Không nhầm ba thứ:

- **JDK đang dùng để build**: kiểm tra bằng `javac -version`.
- **Mức tương thích của class file**: chịu ảnh hưởng bởi `--release`; xem bằng `javap -verbose`.
- **JVM thật sự chạy ứng dụng**: kiểm tra bằng `java -version`.

Trong môi trường cài nhiều JDK, `java` và `javac` có thể trỏ tới **hai phiên bản khác nhau** qua `PATH`/cấu hình công cụ. Chẩn đoán phiên bản phải kiểm tra **cả hai lệnh**, không dựa vào tên thư mục dự án.

## 9. Thư mục, package, classpath và tên class

Ví dụ đầu dùng **default package** để người mới chạy dễ dàng. Trong dự án, bạn thường đặt tên package. Giả sử có:

~~~text
src/
└── demo/
    └── Welcome.java
~~~

Tệp `src/demo/Welcome.java`:

~~~java
package demo;

public class Welcome {
    public static void main(String[] args) {
        System.out.println("Welcome from demo");
    }
}
~~~

Biên dịch vào thư mục output (tạo thư mục `out` trước bằng công cụ file/terminal của hệ điều hành):

~~~bash
javac --release 17 -d out src/demo/Welcome.java
java -cp out demo.Welcome
~~~

Kết quả:

~~~text
Welcome from demo
~~~

Khi có package `demo`, launcher cần **tên đủ điều kiện** `demo.Welcome`; classpath `out` phải trỏ tới **thư mục gốc chứa `demo/`**, không phải thư mục `out/demo`. `javac -d out` sẽ đặt class dưới cấu trúc package phù hợp.

Một số lỗi hay gặp:

- Gõ `java Welcome` dù class thuộc package `demo`.
- Đặt `-cp out/demo` thay vì `-cp out`.
- Chạy lệnh từ thư mục khác với nơi tưởng tượng, làm `.` hoặc `out` trỏ sai.
- Đưa đường dẫn đến `.java` hoặc `.class` thay vì tên class khi đang chạy ở chế độ class.

Classpath còn có thể chứa thư mục và các `.jar` phụ thuộc. Bài này chỉ cần hiểu: **compile cần tìm được các kiểu được tham chiếu; run cần tìm được các class ứng dụng thực sự sử dụng**. Đường dẫn compile và runtime không nhất thiết là một, nên thiếu phụ thuộc có thể chỉ lộ ra lúc chạy.

## 10. Phân loại lỗi theo giai đoạn

| Triệu chứng | Giai đoạn thường gặp | Cách kiểm tra đầu tiên |
|---|---|---|
| `';' expected`, `cannot find symbol`, `incompatible types` | Biên dịch | Kiểm tra tệp nguồn, cú pháp, tên/kiểu và thư viện có trên classpath biên dịch |
| `class HelloPipeline is public, should be declared in a file named HelloPipeline.java` | Biên dịch | Khớp tên public class và tên tệp, kể cả chữ hoa/thường |
| `javac: command not found` hoặc “not recognized” | Trước biên dịch | Kiểm tra cài JDK, `PATH`, terminal đang dùng |
| `Could not find or load main class` | Launcher/class loading | Kiểm tra classpath, package, vị trí file sau biên dịch và tên class |
| `Main method not found` | Khởi động chương trình | Kiểm tra class có phương thức entry point phù hợp, ví dụ `public static void main(String[] args)` |
| `UnsupportedClassVersionError` | Nạp class | So sánh class file target với `java -version` |
| `NoClassDefFoundError` khi gọi chức năng | Runtime/linking/loading | Kiểm tra class phụ thuộc có hiện diện và tương thích tại runtime |
| `NullPointerException`, chia cho 0, lỗi file | Trong lúc thực thi | Đọc stack trace, dữ liệu đầu vào và đường gọi thực tế |

**Phân biệt quan trọng:** `cannot find symbol` từ `javac` là lỗi về mã/tham chiếu ở thời điểm **compile**. `Could not find or load main class` là lỗi trong quá trình **launch/run**: một class có thể đã được biên dịch, nhưng launcher không tìm thấy nó trong classpath yêu cầu.

Nếu lỗi chỉ xuất hiện khi chạy, “biên dịch lại y nguyên” không nhất thiết giải quyết được. Hãy đọc tên exception, thông báo, vị trí trên stack trace và xác minh môi trường chạy.

## 11. Ngoại lệ thú vị: chạy trực tiếp tệp `.java`

Từ Java 11, với source-file launching, có thể chạy một chương trình một tệp đơn giản bằng:

~~~bash
java HelloPipeline.java
~~~

Trong **chế độ này**, launcher yêu cầu biên dịch nguồn phục vụ lần chạy rồi thực thi; bạn không cần tự gọi `javac` trước và không nhất thiết nhận được `.class` được lưu ra đĩa như lệnh `javac` truyền thống.

Vì vậy cần phân biệt:

- `javac HelloPipeline.java` rồi `java HelloPipeline`: **biên dịch trước, chạy class**.
- `java HelloPipeline.java`: **chạy từ tệp nguồn** qua source-file mode (khi môi trường/phiên bản hỗ trợ).

Điều này **không phủ định vai trò của bytecode/JVM**. Trong bài học về chuỗi build và quan sát class file, hãy sử dụng cặp lệnh `javac` + `java` và `javap` trước để thấy rõ các thành phần.

## 12. Edge cases cần biết từ sớm

**1. Sửa source nhưng không build lại.** Khi chạy class mode, JVM đọc bytecode có sẵn, không tự so sánh ngày sửa `.java` để biên dịch thay bạn. Dễ gây nhầm “tại sao chương trình vẫn in kết quả cũ?”.

**2. Compile thành công nhưng thiếu thư viện lúc chạy.** Một class có thể dùng kiểu từ thư viện lúc compile, nhưng khi chạy thiếu `.jar` chứa class cần thiết. Tùy thời điểm JVM cần class ấy, lỗi có thể chỉ xuất hiện khi đi tới chức năng liên quan.

**3. Classpath đúng tệp nhưng sai thư mục gốc.** Với `demo.Welcome`, đưa `out/demo` vào `-cp` là sai vị trí gốc; phải đưa `out`.

**4. Có nhiều class trong một source.** Một tệp Java có thể khai báo thêm các top-level class không public hoặc nested class; `javac` có thể tạo **nhiều tệp `.class`** từ một `.java`. Không suy ra lúc nào cũng có quan hệ một-một giữa file source và class file.

**5. Static initializer bị lỗi.** Một class có thể qua được compile nhưng lỗi lúc JVM khởi tạo class, ví dụ static initialization ném exception. Lỗi này khác hoàn toàn lỗi cú pháp ở `javac`.

**6. Console khác UTF-8.** Đọc source UTF-8 đúng chưa chắc console hiển thị ký tự Unicode đúng. Đây là sự khác biệt giữa bytecode, encoding source và encoding đầu ra.

**7. Chạy JDK quá cũ.** Một JVM không hỗ trợ class file version đã build có thể từ chối nạp file. Hãy chỉnh target/release phù hợp hoặc nâng runtime; đừng chỉnh nội dung bytecode bằng tay.

**8. Không có quyền hoặc thiếu tài nguyên.** Bytecode hợp lệ vẫn có thể thất bại khi truy cập file bị cấm, thiếu cấu hình, cổng mạng đã sử dụng hoặc bộ nhớ bị giới hạn. Compile-time checks không thay thế xử lý lỗi runtime.

## 13. Bài tập thực hành với đáp án kiểm chứng

### Bài A — xác định sản phẩm của từng lệnh

Cho ba lệnh:

~~~bash
javac --release 17 HelloPipeline.java
javap -c HelloPipeline
java -cp . HelloPipeline
~~~

Hãy ghép:

1. Tạo bytecode từ source.
2. Hiển thị thông tin/chỉ thị của bytecode.
3. Nạp và thực thi chương trình trên JVM.

**Đáp án:** 1 là `javac`, 2 là `javap`, 3 là `java`. Lệnh `javap` không thực hiện method `main`.

### Bài B — dự đoán lỗi

Bạn có `src/demo/Welcome.java` khai báo `package demo;`, đã compile `-d out`. Bạn chạy:

~~~bash
java -cp out Welcome
~~~

Điều gì có thể xảy ra? **Đáp án:** launcher không tìm được class có tên `Welcome` ở default package. Lệnh đúng là `java -cp out demo.Welcome`.

### Bài C — nhận diện giai đoạn

Bạn sửa tệp nguồn thành:

~~~java
int number = "sai";
~~~

Bạn nhận được thông báo lỗi ngay khi chạy `javac`. Lỗi xảy ra ở JVM hay compiler? **Đáp án:** trình biên dịch `javac` phát hiện không tương thích kiểu `String` → `int`; `main` không được thực thi vì compilation thất bại.

### Bài D — phiên bản class file

Bạn biên dịch bằng `--release 17` rồi xem `javap -verbose`. Tìm `major version: 61`. Hãy giải thích vì sao Java runtime cũ hơn mức hỗ trợ class file này có thể không chạy được, dù tệp `.class` không chứa đường dẫn Windows/Linux.

**Đáp án:** khả năng chuyển nền tảng của bytecode là một chuyện, khả năng **phiên bản runtime hiểu định dạng class file** là chuyện khác. JVM cần hỗ trợ class file version tương ứng.

### Bài E — chứng minh class file là đầu vào chạy

Sau khi biên dịch `HelloPipeline`, đổi một dòng thông báo trong source rồi chỉ chạy `java HelloPipeline`. Ghi kết quả. Biên dịch lại và ghi kết quả mới.

**Đáp án kỳ vọng:** lần chạy đầu tiếp tục lấy hành vi từ `.class` cũ; sau biên dịch, `.class` cập nhật nên kết quả phản ánh source mới. Đừng nhầm với `java HelloPipeline.java` vì đó là source-file mode.

## 14. Ghi nhớ và tiêu chí hoàn thành

- [ ] Giải thích được **`.java` → `javac` → `.class` → `java`/JVM** bằng lời của mình.
- [ ] Biên dịch và chạy thành công `HelloPipeline.java` trên JDK có hỗ trợ Java 17.
- [ ] Dùng `javap -c` để thấy bytecode mà không nhầm nó với native machine code.
- [ ] Biết khác biệt giữa compile-time error, class loading/launcher error và exception runtime.
- [ ] Hiểu classpath là nơi JVM tìm class, còn package quyết định tên class đầy đủ.
- [ ] Biết `--release` và `java -version` giải quyết hai câu hỏi về tương thích khác nhau.
- [ ] Không khẳng định mọi bytecode đều phải JIT biên dịch; không khẳng định ứng dụng Java chạy được khi không có runtime tương thích.

**Kết luận:** Mã Java không được CPU thực thi trực tiếp từ tệp `.java` trong quy trình build thông thường. `javac` biến mã nguồn thành bytecode chuẩn hóa; launcher `java` và JVM tải, kiểm tra, liên kết, khởi tạo và thực thi các class cần thiết. Nhờ lớp bytecode/JVM, một ứng dụng có thể chuyển nền tảng dễ hơn, nhưng vẫn phải đáp ứng đúng phiên bản runtime, thư viện và điều kiện môi trường.