# Từ tệp `.java` đến bytecode `.class` và quá trình chạy trên JVM

Khi viết một chương trình Java, ta thường bắt đầu bằng một hoặc nhiều tệp nguồn có phần mở rộng `.java`. CPU của máy tính không đọc trực tiếp cú pháp Java như `class`, `if`, `for` hay `System.out.println`. Trước khi chương trình có thể chạy, mã nguồn phải được biên dịch thành một định dạng mà Java Virtual Machine (JVM) hiểu được: **bytecode**, thường được lưu trong tệp `.class`.

Sau đó, JVM tải các lớp cần thiết, kiểm tra và liên kết chúng, khởi tạo lớp, rồi thực thi bytecode. Trong lúc chạy, JVM có thể diễn giải bytecode hoặc biên dịch những đoạn mã thường xuyên được thực thi thành mã máy phù hợp với bộ xử lý hiện tại.

Quy trình tổng quát:

```text
Tệp nguồn .java
      |
      | javac (trình biên dịch Java)
      v
Tệp bytecode .class
      |
      | java (launcher khởi động JVM)
      v
JVM: nạp lớp -> liên kết -> khởi tạo -> thực thi
      |
      +--> Interpreter thực thi bytecode
      |
      +--> JIT biên dịch mã thường chạy thành mã máy
      v
CPU thực thi mã máy trên hệ điều hành hiện tại
```

Để hiểu đúng vai trò của build tool, cần phân biệt ba công việc: **biên dịch mã nguồn**, **tổ chức và đóng gói kết quả build**, và **khởi chạy chương trình**. `javac` đảm nhiệm việc biên dịch Java; Gradle hoặc Maven điều phối các bước build và quản lý classpath; JVM thực thi chương trình.

## 1. Các thành phần tham gia

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Mã nguồn Java | Nội dung do lập trình viên viết | `HelloJvm.java` |
| `javac` | Phân tích và biên dịch mã nguồn thành bytecode | `javac -d out HelloJvm.java` |
| Bytecode | Tập lệnh trung gian theo đặc tả JVM | `HelloJvm.class` |
| Class loader | Tìm và nạp định nghĩa lớp vào JVM | Nạp `com.example.HelloJvm` |
| JVM | Quản lý môi trường chạy và thực thi bytecode | HotSpot JVM trên JDK phổ biến |
| `java` launcher | Khởi động JVM với classpath, tùy chọn và lớp chính được chỉ định | `java -cp out com.example.HelloJvm` |
| Build tool | Quản lý dependency, gọi compiler, kiểm tra và đóng gói ứng dụng | Gradle, Maven |

**JDK (Java Development Kit)** là bộ công cụ phát triển, thường bao gồm compiler `javac`, launcher `java`, các công cụ chẩn đoán và một bản triển khai JVM. JVM là môi trường thực thi theo đặc tả; HotSpot là một triển khai JVM phổ biến. Vì vậy, `javac`, `java` và JVM có liên quan nhưng không phải là cùng một chương trình hay cùng một khái niệm.

## 2. Biên dịch tệp `.java` thành `.class`

### 2.1. Mã nguồn đầu vào

Ví dụ, tạo cấu trúc thư mục sau:

```text
java-demo/
└── src/
    └── com/
        └── example/
            └── HelloJvm.java
```

Nội dung `HelloJvm.java`:

```java
package com.example;

public class HelloJvm {
    private static final String GREETING = "Hello, JVM";

    public static void main(String[] args) {
        int repeat = 2;

        for (int i = 0; i < repeat; i++) {
            System.out.println(GREETING + " - lần " + (i + 1));
        }
    }
}
```

Đây là mã nguồn ở mức ngôn ngữ Java. Nó có tên lớp, khai báo biến, vòng lặp, lời gọi phương thức và các biểu thức. Compiler phải xác định cấu trúc cú pháp, kiểu dữ liệu và ý nghĩa của những biểu thức này trước khi tạo bytecode.

Tên package `com.example` thường được phản ánh qua đường dẫn thư mục `com/example`. Đây là quy ước tổ chức mã nguồn và lớp đã biên dịch; JVM định danh lớp bằng tên đầy đủ có package, chẳng hạn `com.example.HelloJvm`.

### 2.2. Gọi compiler bằng `javac`

Đứng tại thư mục `java-demo`, chạy:

```bash
javac -d out src/com/example/HelloJvm.java
```

Trong đó:

- `javac` là trình biên dịch Java thuộc JDK.
- `-d out` chỉ định thư mục đích để ghi các tệp `.class`.
- `src/com/example/HelloJvm.java` là tệp nguồn đầu vào.

Sau khi biên dịch thành công, cấu trúc kết quả là:

```text
java-demo/
├── src/
│   └── com/example/HelloJvm.java
└── out/
    └── com/example/HelloJvm.class
```

Compiler dùng package để tạo cấu trúc thư mục đầu ra bên dưới `out`. Tùy nội dung nguồn, compiler có thể tạo thêm nhiều tệp `.class`: ví dụ lớp lồng nhau, lớp ẩn danh hoặc một số cấu trúc khác có thể được biểu diễn bằng các class file riêng. Vì thế, không nên mặc định rằng mỗi tệp `.java` luôn tương ứng đúng một tệp `.class`.

Nếu không chỉ định `-d`, `javac` thường ghi tệp `.class` cạnh tệp nguồn tương ứng. Trong dự án thực tế, chỉ định thư mục đầu ra giúp tách mã nguồn và sản phẩm biên dịch, đồng thời giúp build tool quản lý và xóa sản phẩm build dễ dàng hơn.

### 2.3. Compiler làm những gì?

Quá trình biên dịch có thể được hiểu qua các giai đoạn chính sau. Đây là mô hình khái niệm để đọc lỗi và hiểu luồng xử lý; chi tiết nội bộ có thể khác giữa các phiên bản compiler.

1. **Đọc và phân tích từ vựng:** compiler đọc ký tự trong tệp nguồn, nhận diện token như từ khóa `class`, tên định danh, dấu ngoặc, toán tử, literal và dấu chấm phẩy.
2. **Phân tích cú pháp:** compiler kiểm tra các token có tạo thành cấu trúc Java hợp lệ hay không, rồi xây dựng biểu diễn cú pháp của chương trình.
3. **Phân tích ngữ nghĩa và kiểu:** compiler kiểm tra tên lớp, biến, phương thức, quyền truy cập, kiểu dữ liệu, khả năng chuyển kiểu, generic và việc gọi phương thức có hợp lệ hay không.
4. **Xử lý annotation và các bước chuyển đổi cần thiết:** nếu dự án dùng annotation processor, compiler có thể gọi chúng để sinh thêm mã nguồn. Compiler cũng chuyển một số cấu trúc ngôn ngữ cấp cao thành dạng phù hợp hơn cho bytecode.
5. **Sinh bytecode và class file:** compiler tạo các lệnh JVM, bảng hằng, thông tin kiểu và metadata cần thiết, sau đó ghi kết quả thành tệp `.class`.

Ví dụ, nếu viết:

```java
int total = "42";
```

compiler phát hiện lỗi không tương thích kiểu ngay khi biên dịch. JVM chưa được khởi chạy để thực thi dòng lệnh đó. Ngược lại, một lỗi chỉ xuất hiện khi chương trình chạy, chẳng hạn chia cho 0 với số nguyên, có thể vượt qua bước biên dịch và trở thành ngoại lệ lúc runtime.

### 2.4. Biên dịch nhiều tệp và dependency

Một lớp có thể tham chiếu lớp khác. Ví dụ `HelloJvm` gọi `GreetingService`; compiler cần nhìn thấy định nghĩa hoặc bytecode của lớp được tham chiếu để kiểm tra kiểu và chữ ký phương thức.

Với các lớp trong cùng một lần biên dịch, có thể truyền nhiều tệp nguồn:

```bash
javac -d out \
  src/com/example/GreetingService.java \
  src/com/example/HelloJvm.java
```

Nếu lớp phụ thuộc đã được biên dịch trong thư mục `lib-classes` hoặc nằm trong JAR, dùng classpath cho compiler:

```bash
javac -cp "lib/example-library.jar" \
  -d out \
  src/com/example/HelloJvm.java
```

Classpath là danh sách vị trí để công cụ tìm lớp và tài nguyên. Trên Windows, các phần tử classpath được phân tách bằng dấu chấm phẩy (`;`); trên Linux và macOS, dùng dấu hai chấm (`:`). Ví dụ trên dùng dấu phân tách phù hợp với shell Unix.

## 3. Bytecode và cấu trúc tệp `.class`

### 3.1. Bytecode là gì?

Bytecode là tập lệnh trung gian được định nghĩa cho JVM. Mỗi lệnh có opcode và có thể có thêm toán hạng. Nhiều lệnh JVM thao tác trên **operand stack** của frame phương thức: lấy giá trị từ stack, tính toán rồi đẩy kết quả trở lại stack.

Ví dụ, một phép cộng số nguyên có thể được biểu diễn bằng lệnh `iadd`. Một lời gọi phương thức có thể dùng các lệnh như `invokevirtual`, `invokestatic`, `invokeinterface` hoặc `invokespecial`, tùy loại lời gọi. Các lệnh cụ thể được sinh ra phụ thuộc mã nguồn, compiler và phiên bản JDK.

Bytecode không phải mã máy dành riêng cho CPU x86-64 hay ARM64. Nó tuân theo tập lệnh và quy tắc của JVM, vì vậy cùng một class file có thể được các JVM tương thích trên nhiều hệ điều hành và kiến trúc xử lý, miễn là runtime đáp ứng phiên bản class file và các dependency cần thiết.

### 3.2. Các phần chính trong class file

Một tệp `.class` có định dạng nhị phân được quy định bởi đặc tả JVM. Có thể hình dung các phần chính như sau:

| Thành phần | Ý nghĩa |
|---|---|
| Magic number | Bốn byte đầu có giá trị `0xCAFEBABE`, giúp nhận diện class file |
| Minor/major version | Phiên bản định dạng class file mà runtime cần hỗ trợ |
| Constant pool | Các hằng và tham chiếu biểu tượng như tên lớp, tên phương thức, kiểu dữ liệu, chuỗi và số |
| Access flags | Cờ mô tả lớp, ví dụ `public`, `final`, `abstract` |
| This class / super class | Lớp hiện tại và lớp cha |
| Interfaces | Các interface mà lớp triển khai |
| Fields | Mô tả các trường của lớp |
| Methods | Mô tả phương thức, constructor và các thuộc tính liên quan |
| Attributes | Metadata bổ sung như `Code`, `SourceFile`, `LineNumberTable`, `StackMapTable`, annotation và thông tin debug |

Phần `Code` của một phương thức chứa bytecode, giới hạn stack và local variable cần thiết, bảng xử lý ngoại lệ cùng một số thuộc tính phụ trợ. Không phải mọi phương thức đều có `Code`: phương thức `abstract` và phương thức `native` không chứa phần thân bytecode thông thường.

Constant pool có vai trò quan trọng vì bytecode thường tham chiếu tới lớp, trường hoặc phương thức bằng thông tin biểu tượng. JVM có thể giải quyết các tham chiếu này trong giai đoạn liên kết, thường theo nhu cầu khi chương trình chạy.

### 3.3. Quan sát bytecode bằng `javap`

Không cần mở class file bằng trình soạn thảo văn bản. JDK cung cấp `javap`, công cụ đọc và phân tích class file.

```bash
javap -classpath out -c -v com.example.HelloJvm
```

Ý nghĩa các tùy chọn:

- `-classpath out`: tìm lớp trong thư mục `out`.
- `-c`: hiển thị bytecode của từng phương thức.
- `-v`: hiển thị thông tin chi tiết, bao gồm constant pool và thuộc tính class file.

Có thể dùng `-p` để hiển thị cả thành viên không public:

```bash
javap -classpath out -c -p com.example.HelloJvm
```

Kết quả giúp liên hệ mã nguồn với các lệnh JVM. Khi xem kết quả, hãy tập trung vào luồng dữ liệu trên operand stack, các lệnh truy cập trường, lệnh gọi phương thức và các nhánh điều khiển. Không nên coi chuỗi bytecode in ra là một bản dịch một-một cố định của từng dòng Java: compiler có thể tối ưu hoặc chọn cách biểu diễn khác mà vẫn giữ nguyên ngữ nghĩa.

## 4. Khởi chạy chương trình bằng JVM

Sau khi biên dịch, chạy lớp chính bằng lệnh:

```bash
java -cp out com.example.HelloJvm
```

`java` là launcher. Nó đọc tùy chọn dòng lệnh, thiết lập môi trường khởi chạy và tạo JVM để chạy lớp được chỉ định. `-cp out` cung cấp vị trí chứa class file; `com.example.HelloJvm` là tên lớp đầy đủ. Ta không ghi đuôi `.class` và cũng không truyền đường dẫn `out/com/example/HelloJvm.class` ở vị trí tên lớp chính.

JVM tìm phương thức điểm vào phù hợp, thông thường là:

```java
public static void main(String[] args)
```

Đây là quy ước khởi chạy ứng dụng Java truyền thống. `main` là phương thức tĩnh để launcher có thể gọi mà không cần tạo đối tượng của lớp chính trước. Chữ ký được chấp nhận có các quy tắc cụ thể theo phiên bản Java và cách khởi chạy; ví dụ trong bài dùng dạng phổ biến, tương thích rộng.

Sau khi bắt đầu thực thi `main`, JVM tiếp tục nạp các lớp khác khi cần. Một chương trình nhỏ có thể dùng nhiều lớp thư viện, lớp JDK và lớp do ứng dụng định nghĩa. JVM phải tìm đúng phiên bản của tất cả lớp cần thiết trên runtime classpath hoặc module path.

## 5. Các giai đoạn xử lý lớp trong JVM

Đối với một lớp, vòng đời khái quát gồm **loading**, **linking** và **initialization**. Sau đó, mã của các phương thức được thực thi khi chương trình gọi chúng. Các bước này có thể diễn ra vào những thời điểm khác nhau; JVM có thể trì hoãn một số thao tác cho đến khi thật sự cần.

### 5.1. Loading — nạp lớp

Class loader tìm dữ liệu nhị phân của lớp và tạo biểu diễn lớp tương ứng trong JVM. Nguồn dữ liệu có thể là thư mục chứa `.class`, JAR, module, hoặc nguồn tùy chỉnh do class loader cung cấp.

Các class loader nền tảng thường gặp trong JVM hiện đại gồm:

- **Bootstrap class loader:** nạp các lớp nền tảng cốt lõi của Java.
- **Platform class loader:** nạp các lớp nền tảng thuộc những module của JDK.
- **Application class loader:** nạp lớp ứng dụng từ classpath thông thường.

Mô hình delegation phổ biến yêu cầu class loader hỏi loader cha trước khi tự tìm lớp. Cách này giúp các lớp nền tảng được ưu tiên và giảm nguy cơ ứng dụng tự định nghĩa một lớp trùng tên để thay thế lớp cốt lõi. Ứng dụng máy chủ, plugin hoặc framework có thể dùng class loader tùy chỉnh với chính sách riêng.

Danh tính của một lớp trong JVM không chỉ dựa vào tên đầy đủ. Về thực tế, nó còn gắn với class loader đã định nghĩa lớp đó. Hai class loader khác nhau có thể định nghĩa hai lớp cùng tên nhưng JVM xem chúng là hai kiểu khác nhau. Đây là lý do một số lỗi ép kiểu hoặc lỗi tương thích xuất hiện trong môi trường plugin và application server dù tên lớp trông giống hệt nhau.

### 5.2. Linking — liên kết lớp

Liên kết gồm ba hoạt động chính:

1. **Verification — xác minh:** kiểm tra class file có đúng định dạng và bytecode có tuân thủ các quy tắc an toàn của JVM hay không. Ví dụ, verifier kiểm tra kiểu giá trị trên operand stack và tính hợp lệ của luồng điều khiển. Mục đích là ngăn bytecode không hợp lệ làm JVM thực thi các thao tác trái với quy tắc kiểu.
2. **Preparation — chuẩn bị:** tạo các cấu trúc lưu trữ cần thiết cho lớp và thiết lập giá trị mặc định cho các biến lớp (`static`). Các hằng số lớp có thuộc tính `ConstantValue` được xử lý theo quy tắc của đặc tả JVM trong giai đoạn này.
3. **Resolution — phân giải:** chuyển các tham chiếu biểu tượng trong runtime constant pool thành tham chiếu trực tiếp có thể dùng khi thực thi. JVM có thể phân giải một số tham chiếu sớm hoặc trì hoãn đến lần đầu cần dùng.

Phân biệt **giá trị mặc định khi chuẩn bị** với **mã khởi tạo lớp**. Ví dụ, một trường `static int count` ban đầu nhận giá trị mặc định `0`. Biểu thức gán giá trị tùy ý như `static int count = calculateInitialCount();` thuộc quá trình khởi tạo lớp, được thực hiện ở bước initialization.

### 5.3. Initialization — khởi tạo lớp

Khi lớp được khởi tạo, JVM thực hiện các bộ khởi tạo biến lớp và khối `static` theo thứ tự xuất hiện trong mã nguồn, đồng thời bảo đảm lớp cha được khởi tạo trước lớp con theo quy tắc của JVM.

Ví dụ:

```java
class Configuration {
    static int port = readPort();

    static {
        System.out.println("Configuration initialized");
    }

    private static int readPort() {
        return 8080;
    }
}
```

Compiler gom phần khởi tạo tĩnh thành phương thức khởi tạo lớp đặc biệt có tên nội bộ là `<clinit>` khi cần. JVM chạy logic này khi có một thao tác được quy định là chủ động sử dụng lớp, chẳng hạn tạo instance, gọi phương thức `static` được khai báo trong lớp hoặc đọc/ghi một trường `static` không phải hằng số được nội tuyến theo quy tắc của Java.

Một số thao tác chỉ đọc hằng số biên dịch được có thể không kích hoạt khởi tạo lớp khai báo hằng số, vì giá trị đã được compiler đưa trực tiếp vào class file của nơi sử dụng. Do đó, không nên dựa vào việc đọc một hằng số `static final` để bảo đảm khối `static` của lớp sẽ chạy.

Khởi tạo lớp thường chỉ diễn ra một lần cho mỗi định nghĩa lớp trong một class loader. Nếu logic khởi tạo thất bại, lỗi có thể được báo dưới dạng `ExceptionInInitializerError` trong lần khởi tạo đầu tiên; những lần sử dụng sau có thể gặp `NoClassDefFoundError` vì JVM đánh dấu lớp đó ở trạng thái không khởi tạo thành công.

## 6. JVM thực thi bytecode như thế nào?

### 6.1. Interpreter

Interpreter đọc và thực thi các lệnh bytecode. Nó cho phép chương trình bắt đầu chạy mà không cần biên dịch toàn bộ phương thức thành mã máy trước. Cách này thuận tiện cho thời gian khởi động và những đoạn mã chỉ chạy ít lần, nhưng việc diễn giải từng lệnh có thể tốn chi phí khi một đoạn mã được thực hiện lặp đi lặp lại.

### 6.2. JIT compiler

JIT (Just-In-Time) compiler quan sát hành vi thực thi và biên dịch những đoạn mã nóng — thường là phương thức hoặc vòng lặp được gọi nhiều lần — thành mã máy cho CPU hiện tại. Mã máy đã biên dịch có thể được tái sử dụng trong những lần gọi tiếp theo.

JIT có thể tối ưu dựa trên thông tin runtime, chẳng hạn kiểu đối tượng thường gặp hoặc nhánh thường được chọn. Nếu giả định tối ưu không còn đúng, JVM có thể hủy tối ưu hoặc quay lại thực thi ở mức phù hợp. Các triển khai JVM hiện đại thường dùng nhiều tầng biên dịch để cân bằng thời gian khởi động và hiệu năng dài hạn.

Vì vậy, câu nói “JVM thông dịch bytecode” chỉ mô tả một phần. Với JVM như HotSpot, thực thi thực tế thường kết hợp interpreter, JIT và các cơ chế quản lý mã đã biên dịch.

### 6.3. Garbage Collection

Trong lúc chương trình chạy, đối tượng được tạo và lưu trong heap. Khi một đối tượng không còn có thể được truy cập từ các tham chiếu còn sống theo quy tắc của JVM, nó có thể trở thành đối tượng đủ điều kiện để garbage collector thu hồi bộ nhớ.

Garbage Collection (GC) giúp quản lý vòng đời bộ nhớ của đối tượng mà lập trình viên không phải tự giải phóng từng vùng nhớ như trong một số ngôn ngữ khác. GC không bảo đảm rằng một đối tượng sẽ bị thu hồi ngay khi không còn được dùng; thời điểm thu hồi phụ thuộc collector, áp lực bộ nhớ và trạng thái runtime.

## 7. Các vùng dữ liệu runtime của JVM

JVM định nghĩa các vùng dữ liệu runtime để hỗ trợ việc thực thi. Một số vùng được chia sẻ giữa các thread, một số vùng gắn riêng với từng thread.

| Vùng dữ liệu | Phạm vi | Chức năng chính |
|---|---|---|
| Heap | Chia sẻ giữa các thread | Lưu đối tượng và mảng; được quản lý bởi GC |
| Java Virtual Machine Stack | Mỗi thread có stack riêng | Lưu frame của các lần gọi phương thức |
| PC Register | Mỗi thread có một thanh ghi PC riêng | Theo dõi vị trí lệnh đang thực thi của thread |
| Method Area | Vùng logic được chia sẻ | Lưu cấu trúc theo lớp, runtime constant pool, mã phương thức và dữ liệu liên quan |
| Native Method Stack | Thường gắn với thread | Hỗ trợ phương thức native, tùy triển khai JVM |

### 7.1. Heap

Khi thực hiện `new`, đối tượng thường được cấp phát trên heap. Nhiều thread có thể cùng giữ tham chiếu tới một đối tượng. Vì heap được chia sẻ, việc truy cập dữ liệu dùng chung cần tuân thủ các quy tắc đồng bộ và Java Memory Model khi có nhiều thread.

Ví dụ:

```java
User user = new User("An");
```

Biến cục bộ `user` giữ một tham chiếu trong frame của phương thức, còn đối tượng `User` được tạo trên heap theo mô hình thông thường. Khi phương thức kết thúc, frame có thể bị loại bỏ; đối tượng chỉ đủ điều kiện thu hồi nếu không còn đường tham chiếu sống nào tới nó.

### 7.2. Java stack và frame

Mỗi lần gọi phương thức, JVM tạo một frame cho lần gọi đó. Frame chứa các thành phần như:

- **Local variables:** tham số và biến cục bộ được đánh chỉ số.
- **Operand stack:** nơi bytecode đẩy, lấy và thao tác giá trị trung gian.
- **Thông tin hỗ trợ liên kết và trả về:** phục vụ việc gọi phương thức, xử lý kết quả và tiếp tục luồng thực thi.

Khi phương thức gọi phương thức khác, frame mới được đặt lên stack. Khi phương thức kết thúc bình thường hoặc ném ngoại lệ ra ngoài, frame được loại bỏ theo quy tắc xử lý tương ứng.

Đệ quy quá sâu hoặc chuỗi lời gọi phương thức quá lớn có thể làm cạn Java stack và gây `StackOverflowError`. Đây là lỗi liên quan đến giới hạn stack của thread, khác với `OutOfMemoryError` do không cấp phát được bộ nhớ cần thiết.

### 7.3. Method Area và Metaspace

Method Area là khái niệm logic trong đặc tả JVM, dùng để mô tả nơi lưu dữ liệu theo lớp như cấu trúc lớp, runtime constant pool và mã phương thức. Với HotSpot hiện đại, metadata của lớp được quản lý trong vùng native memory gọi là **Metaspace**.

Không nên đồng nhất Method Area với một vùng nhớ vật lý duy nhất có cùng cách triển khai trên mọi JVM. Đặc tả quy định hành vi quan sát được; từng JVM có thể tổ chức bộ nhớ nội bộ khác nhau. Khi Metaspace hoặc heap không đủ, chương trình có thể gặp các dạng `OutOfMemoryError` tương ứng.

## 8. Classpath: tìm lớp khi biên dịch và khi chạy

Compiler và JVM đều cần biết nơi tìm các lớp phụ thuộc. Tuy nhiên, classpath lúc biên dịch và classpath lúc chạy phục vụ hai thời điểm khác nhau:

| Thời điểm | Công cụ | Mục đích |
|---|---|---|
| Compile time | `javac -cp ...` | Tìm lớp cần thiết để kiểm tra kiểu và biên dịch mã nguồn |
| Runtime | `java -cp ...` | Tìm lớp và tài nguyên mà chương trình cần khi chạy |

Một chương trình có thể biên dịch thành công nhưng chạy thất bại nếu runtime classpath thiếu JAR. Ví dụ, compiler đã tìm thấy `example-library.jar`, nhưng lệnh `java` chỉ trỏ tới thư mục `out`; khi chương trình cần nạp lớp từ thư viện, JVM có thể báo `NoClassDefFoundError` hoặc lỗi nạp lớp liên quan.

Có thể truyền nhiều vị trí trên classpath:

```bash
# Linux/macOS
java -cp "out:lib/*" com.example.HelloJvm

# Windows PowerShell hoặc Command Prompt
java -cp "out;lib/*" com.example.HelloJvm
```

Ký tự đại diện `lib/*` cho phép launcher đưa các JAR phù hợp trong thư mục `lib` vào classpath theo quy tắc của Java launcher. Với dự án dùng Java Platform Module System, module path có quy tắc phân giải module riêng và không nên xem nó đơn giản là classpath đổi tên.

Một cách khởi chạy khác là đóng gói ứng dụng thành JAR có manifest khai báo lớp chính:

```bash
java -jar application.jar
```

Trong trường hợp này, launcher đọc thông tin manifest để xác định điểm vào. Cách đóng gói và khai báo dependency đi kèm phụ thuộc cấu hình build tool và định dạng JAR được tạo.

## 9. Build tool đứng ở đâu trong quy trình?

Trong dự án nhỏ, ta có thể tự gọi `javac` rồi `java`. Trong dự án có nhiều module và thư viện, việc tự quản lý hàng trăm tệp nguồn, thứ tự biên dịch, classpath và đóng gói sẽ khó duy trì. Build tool tự động hóa những công việc đó.

Với một dự án Gradle Java thông thường, luồng khái quát là:

```text
src/main/java/**/*.java
          |
          v
      compileJava
          |
          v
build/classes/java/main/**/*.class
          |
          +--> kiểm tra / đóng gói JAR / tác vụ khác
          |
          v
      runtimeClasspath
          |
          v
     JVM chạy ứng dụng
```

Các đường dẫn phổ biến của Java plugin trong Gradle:

- `src/main/java`: mã nguồn chính.
- `src/test/java`: mã nguồn kiểm thử.
- `build/classes/java/main`: class file của mã nguồn chính sau khi biên dịch.
- `build/classes/java/test`: class file của mã nguồn kiểm thử.
- `build/libs`: các artifact như JAR được tạo bởi tác vụ đóng gói.

Ví dụ, từ thư mục gốc dự án Gradle:

```bash
./gradlew clean compileJava
```

Trên Windows có thể dùng:

```powershell
.\gradlew.bat clean compileJava
```

`clean` xóa sản phẩm build do Gradle quản lý; `compileJava` biên dịch mã nguồn chính. Nếu dự án khai báo Application plugin và cấu hình lớp chính, tác vụ `run` có thể khởi chạy ứng dụng với runtime classpath do Gradle xây dựng:

```bash
./gradlew run
```

Trong dự án Spring Boot dùng plugin tương ứng, tác vụ `bootRun` thường được dùng để chạy ứng dụng trong môi trường phát triển:

```bash
./gradlew bootRun
```

Tên tác vụ có sẵn phụ thuộc plugin và cấu hình của dự án. Không phải mọi dự án Gradle đều có `run` hoặc `bootRun`.

Build tool không thay thế JVM. Nó xác định đầu vào, quản lý dependency, chọn JDK/toolchain, gọi compiler và chuẩn bị classpath hoặc artifact. Khi ứng dụng thực sự chạy, vẫn cần một JVM tương thích để nạp và thực thi các lớp.

## 10. Những lỗi thường gặp theo từng giai đoạn

Xác định lỗi thuộc giai đoạn nào giúp chọn đúng công cụ điều tra.

| Lỗi | Thời điểm thường gặp | Nguyên nhân điển hình |
|---|---|---|
| `';' expected`, `cannot find symbol`, lỗi kiểu dữ liệu | Compile time | Cú pháp sai, thiếu import/dependency hoặc dùng API không phù hợp |
| `Could not find or load main class` | Launcher | Tên lớp chính hoặc classpath không đúng |
| `ClassNotFoundException` | Runtime, khi code chủ động nạp lớp | `Class.forName` hoặc class loader không tìm thấy lớp được yêu cầu |
| `NoClassDefFoundError` | Runtime | Lớp cần thiết không có sẵn hoặc trước đó không khởi tạo thành công |
| `UnsupportedClassVersionError` | Loading | JVM đang chạy không hỗ trợ phiên bản class file đã biên dịch |
| `VerifyError` | Verification/linking | Bytecode không hợp lệ hoặc không tương thích với quy tắc verifier |
| `NoSuchMethodError` | Runtime, linking/resolution | Mã đã biên dịch mong đợi phương thức không tồn tại trong phiên bản lớp đang được nạp |
| `ExceptionInInitializerError` | Initialization | Mã khởi tạo tĩnh ném lỗi trong lần khởi tạo đầu tiên |
| `StackOverflowError` | Runtime | Stack của thread không đủ cho chuỗi lời gọi hiện tại |
| `OutOfMemoryError` | Runtime | JVM không thể cấp phát vùng nhớ cần thiết |

Một số lỗi có tên gần nhau nhưng bản chất khác nhau. `ClassNotFoundException` thường là ngoại lệ được ném khi chương trình yêu cầu nạp lớp theo tên và không tìm thấy lớp. `NoClassDefFoundError` là một `LinkageError`, thường xuất hiện khi bytecode cần một định nghĩa lớp mà runtime không thể cung cấp. Cần đọc đầy đủ stack trace và kiểm tra classpath thực tế trước khi kết luận.

## 11. Công cụ quan sát và chẩn đoán

Các lệnh sau giúp xác định công cụ Java đang được dùng và xem kết quả biên dịch:

```bash
java -version
javac -version
javap -classpath out -c -v com.example.HelloJvm
```

Nếu `java -version` và `javac -version` trỏ tới các JDK khác nhau, có thể xảy ra tình trạng biên dịch bằng phiên bản này nhưng chạy bằng phiên bản khác. Hãy kiểm tra `PATH`, `JAVA_HOME` và cấu hình Java toolchain của build tool.

Trên HotSpot, có thể bật log nạp lớp để quan sát lớp được tải từ đâu:

```bash
java -Xlog:class+load=info -cp out com.example.HelloJvm
```

Với một tiến trình Java đang chạy, các công cụ JDK như `jcmd` và `jstack` có thể hỗ trợ điều tra trạng thái VM và thread:

```bash
jcmd <pid> VM.version
jcmd <pid> GC.heap_info
jstack <pid>
```

`<pid>` là mã tiến trình thực tế của ứng dụng. Một số lệnh chẩn đoán hoặc dữ liệu trả về phụ thuộc phiên bản JDK, quyền của người dùng và cấu hình runtime.

Khi debug một ứng dụng được build bằng Gradle, hãy kiểm tra đồng thời ba yếu tố: class file đã được tạo ở đâu, runtime classpath chứa những thư viện nào, và JVM nào đang thực thi ứng dụng. Chỉ nhìn thấy `.class` trong thư mục build chưa chứng minh rằng JVM có thể nạp được toàn bộ dependency.

## 12. Những hiểu lầm cần tránh

| Hiểu lầm | Cách hiểu chính xác |
|---|---|
| Tệp `.class` là mã máy của CPU | `.class` chứa bytecode theo định dạng JVM; JVM mới diễn giải hoặc biên dịch nó thành mã máy phù hợp |
| JVM chỉ là trình thông dịch | JVM hiện đại có thể kết hợp interpreter, JIT compiler, GC và nhiều cơ chế runtime khác |
| Một tệp `.java` luôn tạo đúng một tệp `.class` | Lớp lồng nhau, lớp ẩn danh và cấu trúc khác có thể tạo thêm class file |
| Cài JRE là có đủ mọi công cụ phát triển | `javac` và nhiều công cụ phát triển thuộc JDK; runtime tối thiểu không nhất thiết có compiler |
| Biên dịch thành công nghĩa là chắc chắn chạy được | Runtime còn cần đúng JDK/JVM, dependency, classpath, cấu hình và tài nguyên cần thiết |
| Java chạy trên mọi hệ điều hành mà không có điều kiện | Bytecode có tính di động, nhưng vẫn cần JVM tương thích và các dependency/native library phù hợp |
| Gradle tự thực thi bytecode thay cho JVM | Gradle điều phối build và khởi chạy; ứng dụng Java vẫn được một JVM thực thi |

## 13. Tự lần theo một chương trình từ nguồn đến runtime

Với ví dụ `HelloJvm`, có thể lần theo các câu hỏi sau để kiểm tra mình đã hiểu quy trình:

1. **Nguồn ở đâu?** Xác định package và đường dẫn của `HelloJvm.java`.
2. **Ai biên dịch?** Xem lệnh `javac` hoặc tác vụ `compileJava` mà build tool thực hiện.
3. **Kết quả ở đâu?** Tìm `HelloJvm.class` trong thư mục đầu ra và dùng `javap -c -v` để đọc nội dung.
4. **JVM tìm lớp bằng cách nào?** Kiểm tra tên lớp đầy đủ và classpath hoặc module path của lệnh chạy.
5. **Lớp được xử lý ra sao?** Phân biệt loading, linking và initialization.
6. **Lệnh được thực thi thế nào?** Theo dõi bytecode, interpreter, JIT và các vùng dữ liệu runtime.
7. **Nếu thất bại thì lỗi xuất hiện ở đâu?** Phân loại lỗi compile time, loading/linking, initialization hay runtime.

Khi nắm được chuỗi này, ta có thể đọc log build và stack trace có hệ thống hơn. Một thông báo lỗi từ `javac` thường yêu cầu sửa mã nguồn hoặc dependency lúc biên dịch; lỗi nạp lớp thường yêu cầu kiểm tra classpath và phiên bản runtime; lỗi trong một phương thức đang chạy cần được điều tra qua luồng thực thi và trạng thái ứng dụng.

Điểm cốt lõi là: **`.java` là đầu vào cho compiler, `.class` là bytecode dành cho JVM, còn JVM chịu trách nhiệm đưa chương trình vào runtime và thực thi nó trên máy hiện tại.** Build tool kết nối các bước đó thành một quy trình lặp lại được, có quản lý dependency và artifact rõ ràng.
