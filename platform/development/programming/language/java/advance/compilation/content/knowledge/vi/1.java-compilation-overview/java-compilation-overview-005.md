# Đầu vào, cấu hình, chẩn đoán và đầu ra của một lần biên dịch Java

Một lần biên dịch Java là quá trình biến **mã nguồn** thành **mã bytecode và siêu dữ liệu lớp** để JVM có thể nạp, liên kết và thực thi sau đó. Với công cụ `javac` của JDK, cần phân biệt bốn nhóm: **đầu vào** cung cấp những gì trình biên dịch phải hiểu; **cấu hình** quyết định cách biên dịch; **chẩn đoán** cho biết điều gì đúng hoặc sai; **đầu ra** là các tệp được sinh ra. Nắm rõ bốn nhóm này giúp giải thích được vì sao cùng một mã nguồn có thể biên dịch thành công trên máy này nhưng thất bại hoặc chạy khác trên máy khác.

## 1. Một lần biên dịch diễn ra như thế nào?

Quy trình điển hình:

1. Công cụ nhận danh sách tệp `.java`, các tùy chọn, đường dẫn phụ thuộc và môi trường JDK.
2. Trình biên dịch đọc và giải mã văn bản theo encoding được chọn, tách token, phân tích cú pháp thành cây cú pháp.
3. Nó phân giải tên, import, kiểu, khả năng truy cập, generic, các quy tắc của ngôn ngữ và những API có thể sử dụng theo phiên bản mục tiêu.
4. Nếu được cấu hình, annotation processors có thể phân tích phần tử chương trình và tạo thêm mã nguồn hoặc tài nguyên; các vòng xử lý liên quan sẽ diễn ra trước khi hoàn tất biên dịch.
5. Sau các kiểm tra cần thiết, trình biên dịch tạo tệp `.class` cho những kiểu cần phát sinh bytecode, đồng thời phát ra lỗi/cảnh báo/thông tin.
6. Công cụ báo trạng thái thành công hay thất bại. Việc **chạy** chương trình bằng `java` là bước khác: JVM nạp lớp và có thể còn phát sinh lỗi lúc liên kết hoặc lúc thực thi.

Đây là mô hình khái quát; thứ tự nội bộ của các pha, số lượt xử lý và tối ưu hóa có thể khác giữa phiên bản hoặc bản cài đặt trình biên dịch. Không nên hiểu `javac` là công cụ biến thẳng `.java` thành mã máy native.

## 2. Đầu vào: trình biên dịch cần những gì?

| Đầu vào | Vai trò | Ví dụ |
| --- | --- | --- |
| Mã nguồn | Các compilation unit chứa `package`, `import`, khai báo kiểu và câu lệnh | `src/demo/Main.java` |
| API và kiểu đã biên dịch | Giải quyết tham chiếu đến lớp, giao diện, phương thức, trường | `.class` trong thư mục hoặc `.jar` |
| Thư viện module | Cung cấp các named module trên module path | JAR modular, thư mục module |
| Cấu hình trình biên dịch | Quy định release, encoding, nơi xuất bytecode, cảnh báo, processor | `--release 17`, `-d out` |
| Bộ xử lý annotation (nếu dùng) | Kiểm tra annotation và có thể sinh mã nguồn hoặc tài nguyên | Processor trên processor path |
| Nền tảng JDK | Cung cấp chính `javac` và API nền tảng được phép truy cập | JDK 17, 21, ... |

**Mã nguồn trực tiếp** là những tệp truyền vào lệnh `javac`. Trình biên dịch có thể tìm và biên dịch thêm mã nguồn phụ thuộc theo cấu hình đường dẫn; vì vậy số tệp `.class` sinh ra có thể lớn hơn số `.java` được liệt kê. Mỗi tệp `.java` cũng có thể khai báo thêm kiểu top-level không phải `public` và các kiểu lồng nhau.

**Classpath (`-cp`/`-classpath`/`--class-path`)** là nơi tìm các lớp và thư viện của mô hình unnamed module/truyền thống. Thư mục chứa bytecode và JAR là hai dạng phần tử phổ biến. `--module-path` dùng để tìm named module trong hệ thống module Java; hai cơ chế có các quy tắc đọc/khả năng truy cập khác nhau. Không giải quyết lỗi module bằng cách tùy tiện chuyển mọi thư viện sang classpath.

**Source path (`-sourcepath`/`--source-path`)** điều khiển nơi trình biên dịch tìm tệp nguồn cho những kiểu chưa được truyền trực tiếp. Nó khác classpath, vốn dùng để tìm kiểu đã biên dịch. Nên khai báo rõ các nguồn trong quy trình build để tránh việc biên dịch ngầm phụ thuộc vào bố cục thư mục hoặc trạng thái máy.

**Encoding** là một phần của đầu vào: cùng dãy byte có thể được đọc thành ký tự khác nhau nếu dùng bảng mã khác. Với mã nguồn UTF-8, chỉ định `-encoding UTF-8` giúp kết quả ổn định hơn giữa các môi trường. Encoding của tệp nguồn, encoding khi in ra terminal và encoding của tài nguyên runtime là ba vấn đề riêng.

**Tài nguyên runtime** như `.properties`, ảnh hoặc file cấu hình nhìn chung không được `javac` tự đưa vào thư mục bytecode. Build tool thường có bước copy resource độc lập. `javac` cũng không tự tải thư viện từ Maven Central: Maven/Gradle hoặc thao tác khác phải giải quyết thư viện trước.

## 3. Cấu hình: những tùy chọn quyết định kết quả

Cú pháp cơ bản:

```text
javac [options] <source-files>
java [runtime-options] <main-class>
```

Trong các lệnh bên dưới, `javac` đến từ **JDK**, còn `java` dùng để chạy bytecode. Các lệnh cần được thực thi từ đúng thư mục dự án.

| Tùy chọn `javac` | Ý nghĩa thực tế | Điều cần nhớ |
| --- | --- | --- |
| `--release 17` | Biên dịch với ngữ pháp, bytecode và API công khai của Java 17 | Cần JDK hỗ trợ mục tiêu đó; thích hợp hơn việc chỉ đặt `-target` khi cần tương thích |
| `-source 17` | Quy định mức cú pháp nguồn | Không tự giới hạn API thư viện theo JDK đích |
| `-target 17` | Quy định phiên bản class file | Không thay thế đầy đủ `--release` |
| `-encoding UTF-8` | Đọc tệp `.java` bằng UTF-8 | Không chi phối encoding mọi dữ liệu lúc chương trình chạy |
| `-d out` | Ghi class file vào thư mục `out` | Tạo sẵn thư mục đích; package thành đường dẫn con |
| `-cp libs/example.jar` | Chỉ định nơi tìm phụ thuộc trên classpath | Khi nhiều phần tử: dấu `;` trên Windows, dấu `:` trên Unix |
| `--module-path mods` | Nơi tìm named modules | Chỉ phát huy đúng khi cấu trúc/module được khai báo phù hợp |
| `-sourcepath src` | Nơi tìm thêm mã nguồn phụ thuộc | Phân biệt với classpath |
| `-Xlint:all` | Bật các nhóm cảnh báo `javac` hỗ trợ | Có thể chọn nhóm cụ thể như `unchecked` hoặc `deprecation` |
| `-Werror` | Coi cảnh báo của trình biên dịch là lỗi build | Có thể làm build thất bại dù chương trình không có syntax error |
| `-Xdiags:verbose` | Chi tiết hóa thông báo chẩn đoán | Hữu ích khi generic hoặc overload dẫn tới lỗi khó hiểu |
| `-g` / `-g:none` | Điều chỉnh debug info trong class file | Ảnh hưởng việc debug, không thay đổi logic nguồn dự kiến |
| `-parameters` | Ghi tên tham số phương thức cho reflection | Khác với tên biến cục bộ trong debug info |
| `-s generated` | Chọn nơi ghi mã nguồn do annotation processor tạo | Chỉ có tác dụng khi thực sự có generated source |
| `-proc:none` | Vô hiệu hóa annotation processing | Dùng khi cần kiểm soát hoặc cô lập processor |
| `-h headers` | Sinh native header cho phương thức native khi cần | Không phải đầu ra bắt buộc của mọi chương trình |

Khi mục tiêu là tương thích Java 17, ví dụ `javac --release 17 ...` trên JDK có hỗ trợ Java 17 là lựa chọn rõ nghĩa. Tránh kết hợp `--release` với `-source`/`-target` cho cùng một lần gọi. Biên dịch thành class file phiên bản 17 **không chứng minh** toàn bộ ứng dụng chạy được trên một JVM cụ thể: phụ thuộc bên ngoài, tài nguyên, cấu hình và hành vi runtime vẫn phải được kiểm tra.

`-cp` ở bước **biên dịch** và `-cp` ở bước **chạy** phục vụ hai giai đoạn khác nhau. Chạy chương trình cũng cần các phụ thuộc runtime cần thiết, ngay cả khi giai đoạn biên dịch đã thành công.

## 4. Ví dụ đầu-cuối: biên dịch hai lớp Java 17

Giả sử cấu trúc dự án ban đầu như sau:

```text
project/
└── src/
    └── demo/
        ├── Calculator.java
        └── Main.java
```

Tệp `src/demo/Calculator.java`:

```java
package demo;

public final class Calculator {
    private Calculator() {
    }

    public static int add(int left, int right) {
        return left + right;
    }
}
```

Tệp `src/demo/Main.java`:

```java
package demo;

public final class Main {
    public static void main(String[] args) {
        int result = Calculator.add(2, 3);
        System.out.println("Kết quả: " + result);
    }
}
```

Từ thư mục `project`, tạo nơi nhận class file rồi biên dịch **cả hai** tệp:

```sh
mkdir out
javac --release 17 -encoding UTF-8 -d out src/demo/Calculator.java src/demo/Main.java
java -cp out demo.Main
```

Khi biên dịch thành công, `javac` thường không in dòng thông báo nào. **Stdout của lệnh `java` cuối cùng chính xác là:**

```text
Kết quả: 5
```

Đầu ra bytecode sau khi biên dịch:

```text
out/
└── demo/
    ├── Calculator.class
    └── Main.class
```

Các điểm cần quan sát:

- `package demo;` làm cho tên nhị phân của lớp là `demo.Main`, và với `-d out` file được đặt dưới `out/demo`.
- `java -cp out demo.Main` dùng **tên lớp đầy đủ**; không truyền đường dẫn `out/demo/Main.class` vào vị trí tên main class.
- `--release 17` chọn đích Java 17; các class file ở ví dụ này có major version **61**. Có thể kiểm tra bằng `javap -verbose -classpath out demo.Main` và tìm `major version: 61`.
- `javac` không tự chạy phương thức `main`. Stdout ở trên xuất hiện khi thực hiện `java`.
- Nếu bỏ `-d out`, vị trí file sinh ra phụ thuộc cách tổ chức nguồn và tùy chọn còn lại; chỉ định thư mục output giúp dễ quản lý.
- Chạy lại lệnh `javac` trên thư mục output cũ có thể để lại file từ lần build trước. Khi kiểm tra tính tái lập, hãy dùng thư mục output sạch được quản lý bởi build tool hoặc quy trình build chủ động.

**Vì sao phải biên dịch đủ nguồn?** Lớp `Main` tham chiếu `Calculator`. Nếu chỉ truyền `Main.java`, khả năng tìm `Calculator` còn phụ thuộc nơi công cụ tìm nguồn/bytecode. Liệt kê tường minh hai tệp hoặc cấu hình source path đúng giúp kết quả ít phụ thuộc môi trường hơn.

## 5. Chẩn đoán: đọc lỗi và cảnh báo theo đúng giai đoạn

`javac` có thể phát ra:

- **Error**: vi phạm khiến đơn vị biên dịch không thể tạo ra kết quả hợp lệ, ví dụ cú pháp sai, kiểu không tương thích, không tìm được symbol, truy cập thành viên không hợp lệ, thiếu module hoặc phụ thuộc.
- **Warning**: điều đáng lưu ý nhưng chưa chắc cản trở việc biên dịch, như raw/unchecked generic, API deprecated, một số bất thường được `-Xlint` phát hiện. Dùng `-Werror` khiến cảnh báo làm lệnh biên dịch thất bại.
- **Note/thông điệp khác**: thông tin do trình biên dịch hoặc annotation processor phát ra, không mặc nhiên là lỗi.

Ví dụ tệp `src/demo/Broken.java`:

```java
package demo;

public class Broken {
    public static void main(String[] args) {
        int total = "five";
        System.out.println(total);
    }
}
```

Lệnh:

```sh
javac --release 17 -encoding UTF-8 -d out src/demo/Broken.java
```

Một thông báo lỗi điển hình (dấu cách, cách trình bày và chi tiết có thể khác theo JDK/tùy chọn):

```text
src/demo/Broken.java:5: error: incompatible types: String cannot be converted to int
        int total = "five";
                    ^
1 error
```

Đọc thông báo từ trái sang phải: **tệp nguồn → dòng (có thể thêm cột) → mức độ → bản chất lỗi → vị trí liên quan**. Ở đây không thể gán `String` vào biến `int`; sửa mã nguồn, chẳng hạn `int total = 5;`, rồi biên dịch lại. Việc thay đổi classpath sẽ không chữa lỗi không tương thích kiểu này.

Bảng phân biệt nguồn gốc sự cố:

| Triệu chứng | Giai đoạn thường liên quan | Câu hỏi kiểm tra |
| --- | --- | --- |
| `';' expected`, `illegal start of expression` | Phân tích cú pháp nguồn | Dấu ngoặc, dấu chấm phẩy, cú pháp hợp lệ với `--release`? |
| `cannot find symbol` | Phân giải tên/kiểu | Tên sai, thiếu import, thiếu nguồn hoặc classpath? |
| `package ... does not exist` | Phân giải package/thư viện | JAR có đúng nội dung, phiên bản, đường dẫn? |
| `incompatible types` | Kiểm tra kiểu | Giá trị trả về/generic/chuyển kiểu có hợp lệ? |
| `module not found` | Phân giải module | `module-info.java` và `--module-path` đã đúng? |
| Cảnh báo `unchecked` | Kiểm tra generic | Có raw type hoặc phép chuyển kiểu không được kiểm chứng? |
| `UnsupportedClassVersionError` | Lúc nạp/chạy class, **sau** biên dịch | JVM runtime có hỗ trợ version class file? |
| `NoClassDefFoundError` | Lúc nạp/chạy class, **sau** biên dịch | Thiếu lớp ở runtime classpath/module path? |

Hai dòng cuối minh họa lỗi **runtime/linkage**, không phải thông báo compiler của một lần chạy `javac` thông thường. Tương tự, `NullPointerException` hoặc lỗi nghiệp vụ xuất hiện lúc chạy không thể được diễn giải là lỗi cú pháp lúc biên dịch.

Khi tìm nguyên nhân một lỗi build:

1. Chụp lại **lệnh `javac` thực tế**, phiên bản `javac -version`, toàn bộ stderr, working directory và các đường dẫn phụ thuộc cần thiết.
2. Đọc **lỗi đầu tiên có nguyên nhân rõ ràng** trước: một lỗi khai báo hoặc thiếu dependency có thể tạo ra nhiều lỗi theo sau.
3. Phân loại lỗi thuộc mã nguồn, release/API, classpath/module path, encoding hay annotation processing.
4. Chỉnh đúng nguyên nhân, build lại và kiểm tra exit code, không chỉ kiểm tra có xuất hiện `.class` cũ.
5. Dùng `-Xdiags:verbose` hoặc `-Xlint:unchecked`/`-Xlint:deprecation` khi cần nhiều thông tin hơn.

**Mã thoát của lệnh:** thông thường `javac` trả 0 khi hoàn tất thành công và khác 0 khi thất bại. Shell/build system nên quyết định thành bại dựa vào exit code; không dựa vào việc stdout rỗng. Compiler thường ghi diagnostics ra stderr trong cách gọi CLI mặc định, nhưng công cụ tích hợp có thể thu thập và hiển thị chúng theo cách khác. Không coi vị trí file tồn tại là bằng chứng lần biên dịch hiện tại thành công.

## 6. Đầu ra: bytecode, metadata và artifact đóng gói

**`.class` là đầu ra chính**. Nó chứa cấu trúc class file JVM, constant pool, thông tin kiểu/thành viên, bytecode của các phương thức có code, thuộc tính như source/debug info và annotation phù hợp. Một tệp `.java` có thể phát sinh nhiều `.class`; ví dụ lớp lồng nhau thường có tên file chứa dấu `$`. Không phải mọi khai báo đều sinh đúng một class file theo cách nhìn từ mã nguồn.

**Generated sources/resources** chỉ xuất hiện khi annotation processors hoặc công cụ sinh mã tương ứng được kích hoạt. Tùy cấu hình, nguồn sinh có thể được viết dưới thư mục chọn bằng `-s`, còn lớp biên dịch vẫn nằm tại thư mục `-d`. Đừng nhầm tệp Java được sinh ra với class file, và đừng tự ý commit thư mục generated mà build quy định quản lý.

**Native headers** có thể được phát sinh bằng `-h` khi ứng dụng dùng cách tích hợp native tương ứng; đây không phải sản phẩm mặc định của một bài Java thuần.

**JAR** là bước **đóng gói sau biên dịch**, không phải thứ mà `javac -d` tự tạo. Từ ví dụ thành công ở mục 4, có thể làm:

```sh
jar --create --file demo.jar --main-class demo.Main -C out .
java -jar demo.jar
```

Stdout của `java -jar demo.jar` trong ví dụ này vẫn là:

```text
Kết quả: 5
```

Tùy chọn `--main-class` ghi điểm vào chương trình trong manifest của JAR. Nếu không có entry point thích hợp, `java -jar` không biết chạy lớp nào. Một JAR có thể cần thêm dependency hoặc cấu hình; ví dụ này không có thư viện bên ngoài nên chạy trực tiếp được. Khác với `java -cp ...`, khi dùng `java -jar` thì classpath do tham số `-cp` của launcher không quyết định phụ thuộc của ứng dụng JAR đó; manifest hoặc cách đóng gói/launcher khác phải xử lý chúng.

**Tệp còn sót sau lỗi:** không dựa vào giả định rằng mọi build thất bại sẽ xóa sạch output. Với nhiều tệp nguồn hoặc nhiều tác vụ build, thư mục output có thể chứa artifact từ lần trước hoặc artifact được ghi trước khi lỗi xảy ra. Khi cần bằng chứng cho một lần biên dịch, dùng output mới, ghi nhận exit code và kiểm tra artifact đúng build.

## 7. Biên dịch qua build tool hoặc Compiler API

Trong dự án lớn, Maven/Gradle/IDE thường là lớp điều phối. Chúng tìm nguồn, giải quyết phụ thuộc, chọn Java toolchain/release, cấu hình processors, gọi compiler, copy resources, chạy kiểm thử và đóng gói. Vì thế, một lỗi hiện trên Gradle/Maven có thể thuộc **lớp giải quyết dependency/cấu hình build**, chưa chắc đã do cú pháp Java. Khi debug nên tìm invocation và diagnostics của tác vụ biên dịch cụ thể.

Java cũng cung cấp **Java Compiler API** trong `javax.tools`, điển hình là:

- `ToolProvider.getSystemJavaCompiler()` để lấy compiler có trong môi trường JDK thích hợp; có thể trả `null` nếu môi trường không cung cấp system compiler.
- `JavaCompiler.getTask(...)` để truyền option, compilation units và file manager; gọi `call()` để biết tác vụ thành công hay không.
- `DiagnosticCollector<JavaFileObject>` để thu thập các diagnostics có mức độ, tệp, dòng, cột, mã và thông điệp.
- `StandardJavaFileManager` để quản lý nguồn, bytecode và đường dẫn đầu vào/đầu ra.

IDE và build plugin có thể dùng Compiler API hoặc cơ chế tích hợp khác; đừng mặc định mọi diagnostic sẽ xuất hiện trong terminal. Dù gọi qua API, các khái niệm về source, release, classpath/module path, processor, output và lỗi vẫn giống nhau.

### Annotation processing là bước có cấu hình và tác động riêng

Một annotation processor có thể tạo thêm nguồn, resource hoặc báo lỗi/cảnh báo; nó chạy **trong quá trình build** và có thể thực thi mã của thư viện build. Cách tự động tìm/chạy processor thay đổi theo phiên bản JDK và thiết lập build. Với dự án thực tế, nên khai báo processor và processor path tường minh qua build tool, kiểm tra phiên bản processor, và tránh coi mọi JAR ở classpath là đáng tin cậy để chạy trong build. `-proc:none` hữu ích khi cần xác định xem sự cố có đến từ processor.

## 8. Các lỗi hiểu nhầm thường gặp

**“Biên dịch thành công thì chạy chắc chắn thành công.”** Sai: JVM đích có thể cũ hơn class file, thiếu phụ thuộc runtime, thiếu tài nguyên hoặc có lỗi logic. Kiểm tra cả compile và run trên môi trường mục tiêu.

**“Đã đặt `-target 17` thì mọi API đều tương thích Java 17.”** Không đủ: một JDK mới hơn có thể cho phép nguồn gọi API không có ở 17. Nếu JDK hỗ trợ, dùng `--release 17` để có ràng buộc API nền tảng tương ứng; phụ thuộc bên ngoài vẫn cần kiểm tra riêng.

**“`cannot find symbol` luôn nghĩa là thiếu import.”** Nó cũng có thể do tên sai, modifier, khai báo không hợp lệ, nguồn phụ thuộc không được tìm thấy hoặc classpath sai. Đọc đúng symbol và context trong diagnostic.

**“`javac` xuất một JAR.”** `javac` tạo class files và một số output tùy chọn; `jar` hoặc công cụ build thực hiện đóng gói.

**“Source path, classpath và module path dùng thay thế nhau.”** Mỗi đường dẫn phục vụ cơ chế phân giải khác nhau. Trong dự án modular, cần hiểu `module-info.java` và quan hệ đọc module; trong dự án không modular, phải chỉ rõ những JAR/class cần thiết trên classpath.

**“Cứ có file `.class` nghĩa là lần compile mới nhất đã thành công.”** File cũ có thể còn lại; kiểm tra exit code và đầu ra của đúng lần build.

**“`-parameters` và `-g` giống nhau.”** `-parameters` lưu metadata tên tham số để reflection truy cập; `-g` điều chỉnh debug info. Đây là các mục đích khác nhau.

## 9. Checklist để giải thích và tái lập một lần biên dịch

Trước khi kết luận một lần biên dịch là chính xác, có thể tự trả lời:

1. **Đầu vào:** Những `.java` nào được biên dịch? Cần class/JAR/module/source/processor nào? Resource runtime do bước nào xử lý?
2. **Môi trường:** `javac -version` là gì? Thư mục hiện tại ở đâu? Tệp nguồn đang dùng encoding nào?
3. **Cấu hình:** `--release`, `-d`, classpath/module path, source path và lint/processor options thực tế là gì?
4. **Chẩn đoán:** Exit code bao nhiêu? Error/warning xuất phát từ tệp/dòng/symbol nào? Có bị `-Werror` làm build fail không?
5. **Đầu ra:** Class file nào mới được tạo? Có generated source, native header hay JAR không? Artifact có thuộc đúng lần build này không?
6. **Kiểm chứng:** Chạy đúng tên lớp hoặc entry point trên runtime đích và xác thực stdout/hành vi; phân biệt lỗi compile với lỗi chạy.

Nắm đủ bốn nhóm **input → configuration → diagnostics → output** sẽ giúp tái hiện chính xác một lần `javac`, tìm đúng chỗ sai và tránh suy đoán từ một dòng lỗi hoặc một file `.class` tình cờ tồn tại.