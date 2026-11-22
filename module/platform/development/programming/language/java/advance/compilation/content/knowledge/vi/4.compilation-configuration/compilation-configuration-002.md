# Biên dịch ngầm phụ thuộc nguồn và tùy chọn `-implicit` của `javac`

Trong một dự án Java, câu lệnh biên dịch có thể chỉ liệt kê một tệp `.java`, nhưng `javac` lại cần đọc thêm các kiểu được dùng bởi tệp đó. Nếu tìm thấy mã nguồn của một kiểu phụ thuộc, compiler có thể **biên dịch ngầm** mã nguồn ấy và sinh thêm `.class` dù tệp không được liệt kê trên dòng lệnh. Tùy chọn `-implicit:class` hoặc `-implicit:none` kiểm soát **việc sinh `.class` cho tệp nguồn được tìm thấy ngầm**.

Hiểu đúng cơ chế này rất quan trọng khi tổ chức mã nguồn, viết lệnh biên dịch thủ công, chẩn đoán vì sao một thư mục output có thêm hoặc thiếu lớp, phối hợp với annotation processor và xây dựng quy trình build tái lập. Bài học áp dụng trực tiếp cho `javac` trên Java 17+; các ví dụ được kiểm tra bằng JDK 21.

## 1. Phân biệt nguồn được chỉ định tường minh và nguồn được phát hiện ngầm

Xét lệnh:

```bash
javac -sourcepath src -d out src/demo/App.java
```

Ở đây `src/demo/App.java` là **đầu vào tường minh**: người gọi yêu cầu biên dịch nó. Nếu `App` dùng `demo.Greeting`, compiler cần khai báo của `Greeting` để kiểm tra tên, quyền truy cập, kiểu tham số và kiểu trả về. Nó có thể tìm thấy `Greeting.class` đã biên dịch hoặc `src/demo/Greeting.java` thông qua đường dẫn tìm kiếm.

Khi compiler chọn đọc `Greeting.java` để lấy thông tin kiểu dù tệp ấy không được nêu trong lệnh, đây là **nguồn được phát hiện ngầm** (implicitly referenced/loaded source). Theo hành vi mặc định, `javac` cũng sinh `Greeting.class`. Nhưng **được đọc để phân tích kiểu** và **được sinh class file** là hai hành vi cần phân biệt.

Ví dụ về các phụ thuộc có thể khiến compiler phải tìm thông tin kiểu:

- `new Greeting()`, gọi phương thức tĩnh `Greeting.message()` hoặc truy cập một trường;
- `extends BaseClass`, `implements Interface`, chữ ký phương thức và kiểu của tham số;
- kiểu không xuất hiện trực tiếp trong dòng nguồn đang xem nhưng cần để phân giải một quan hệ kế thừa hoặc một lời gọi.

Đồ thị phụ thuộc để kiểm tra kiểu có thể rộng hơn danh sách tệp mà người dùng truyền cho `javac`.

```text
Lệnh: javac ... App.java
                     |
                     v
                  App.java  (nguồn tường minh)
                     |
            cần khai báo Greeting
                     |
             +-------+-------+
             |               |
       Greeting.class   Greeting.java
       (nếu chọn class) (nếu chọn source)
                             |
                      -implicit:class
                      -> có thể sinh Greeting.class
                             |
                      -implicit:none
                      -> không sinh Greeting.class ngầm
```

Sơ đồ là đường đi khái niệm; việc compiler chọn `.java` hay `.class` còn phụ thuộc vị trí, thời gian sửa đổi và tùy chọn tìm kiếm.

## 2. `-implicit:class` và `-implicit:none` thực sự làm gì?

| Chế độ | Tệp nguồn được nêu trực tiếp trong lệnh | Tệp nguồn compiler tìm thấy ngầm | Kết quả cần nhớ |
| --- | --- | --- | --- |
| Không truyền `-implicit` | Biên dịch và sinh `.class` theo lệnh | Mặc định cũng sinh `.class` | Có thể xuất hiện file output từ nguồn không nằm trong danh sách lệnh |
| `-implicit:class` | Biên dịch và sinh `.class` | Cho phép sinh `.class` | Nói rõ ý định dùng hành vi tự động |
| `-implicit:none` | Vẫn biên dịch và sinh `.class` | Không sinh `.class` cho nguồn được tải ngầm | **Không** cấm compiler đọc hay phân tích mã nguồn phụ thuộc |

Điểm dễ nhầm nhất: **`-implicit:none` không có nghĩa là “không được phép sử dụng tệp nguồn khác”, cũng không tương đương “chỉ kiểm tra kiểu trong tệp duy nhất”.** Compiler vẫn có thể đọc và phân tích một nguồn phụ thuộc để xác nhận chương trình hợp lệ; chỉ việc sinh class file của nguồn ngầm bị chặn.

Ngoài ra, `-implicit:none` không làm cho các class đã tồn tại trong `-classpath` biến mất, không ngăn một annotation processor tạo source trong luồng riêng của nó, và không đảm bảo tập class output hoàn chỉnh để chạy chương trình. Nếu muốn kiểm soát đầu vào tường minh, phải quản lý danh sách `.java`, source path và classpath cùng nhau.

Cả hai giá trị là một tùy chọn `javac`; có thể viết:

```bash
javac -implicit:class ...
javac -implicit:none ...
```

Không có `-implicit:true` hay `-implicit:false` theo cú pháp này.

## 3. Ví dụ Java 17+ tự chạy: một đầu vào và một nguồn phụ thuộc

Tạo cấu trúc thư mục:

```text
example/
└── src/
    └── demo/
        ├── App.java
        └── Greeting.java
```

Nội dung `src/demo/App.java`:

```java
package demo;

public class App {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
```

Nội dung `src/demo/Greeting.java`:

```java
package demo;

public final class Greeting {
    private Greeting() {
    }

    static String message() {
        return "Hello from Greeting";
    }
}
```

Ở thư mục `example`, tạo **ba thư mục output rỗng** bằng ba lệnh sau (dùng được trong Bash, PowerShell hoặc Command Prompt):

```text
mkdir out-class
mkdir out-none
mkdir out-explicit
```

Mỗi lần chạy ví dụ nên bắt đầu từ output rỗng: class file còn sót từ lần thử khác có thể làm sai kết luận.

### Trường hợp A: cho phép sinh class file ngầm

```bash
javac -encoding UTF-8 -sourcepath src -d out-class -implicit:class src/demo/App.java
java -cp out-class demo.App
```

Stdout chính xác:

```text
Hello from Greeting
```

Trong một thư mục output ban đầu trống, hai tệp sẽ xuất hiện:

```text
out-class/demo/App.class
out-class/demo/Greeting.class
```

`App.java` là source tường minh; `Greeting.java` chỉ được tìm thấy vì `App` cần kiểu `Greeting`. `-implicit:class` cho phép compiler sinh `Greeting.class` cùng với `App.class`.

### Trường hợp B: chặn sinh class file của nguồn ngầm

```bash
javac -encoding UTF-8 -sourcepath src -d out-none -implicit:none src/demo/App.java
```

Lệnh biên dịch **thành công**, nhưng từ output rỗng chỉ có:

```text
out-none/demo/App.class
```

`Greeting.java` đã cung cấp đủ thông tin để kiểm tra và biên dịch `App`, nhưng `Greeting.class` không được tạo. Nếu chạy:

```bash
java -cp out-none demo.App
```

chương trình sẽ thất bại khi cần `Greeting`, thường với `NoClassDefFoundError: demo/Greeting` (chuỗi stack trace đầy đủ có thể khác theo JDK). **Biên dịch thành công không đồng nghĩa có đủ class file để chạy.** Sự thất bại này xuất phát từ runtime classpath không chứa `Greeting.class`, không phải từ việc `-implicit:none` làm Java bytecode của `App` trở nên bất hợp lệ.

### Trường hợp C: chỉ định tường minh cả hai nguồn

```bash
javac -encoding UTF-8 -sourcepath src -d out-explicit -implicit:none src/demo/App.java src/demo/Greeting.java
java -cp out-explicit demo.App
```

Stdout chính xác:

```text
Hello from Greeting
```

Lần này có cả hai:

```text
out-explicit/demo/App.class
out-explicit/demo/Greeting.class
```

`-implicit:none` **không** loại bỏ output của `Greeting` vì `Greeting.java` đã được liệt kê tường minh. Đây là cách phân biệt rõ nhất giữa *nguồn phụ thuộc tìm thấy ngầm* và *nguồn người gọi yêu cầu biên dịch*.

## 4. `javac` tìm nguồn phụ thuộc ở đâu?

Các đường dẫn hay gặp khi biên dịch Java theo classpath (chưa dùng cấu trúc module):

| Tùy chọn | Vai trò |
| --- | --- |
| `-sourcepath src` hoặc `--source-path src` | Nơi tìm các `.java` bổ sung theo cấu trúc package khi cần khai báo kiểu |
| `-classpath libs` / `-cp libs` | Nơi tìm `.class` của thư viện và các kiểu đã biên dịch |
| `-d out` | Địa chỉ ghi class file đầu ra; **không tự động** có nghĩa `out` được thêm vào classpath |
| `-implicit:class` / `-implicit:none` | Có sinh `.class` cho **nguồn được tìm thấy ngầm** hay không |

Với lệnh ví dụ `-sourcepath src`, khi cần `demo.Greeting`, compiler tìm nguồn theo đường dẫn tương ứng `src/demo/Greeting.java`; từ đó nó phân tích khai báo kiểu. Đường dẫn đến source cần phù hợp tên package.

Nếu **không** thiết lập source path riêng khi biên dịch kiểu classpath, `javac` cũng có thể tìm `.java` trong user classpath. Đây là lý do một lệnh chạy ở thư mục khác hoặc có `CLASSPATH` khác có thể nhận được tập source phụ thuộc không giống nhau. Dùng `-sourcepath` và `-classpath` tường minh giúp giảm đầu vào không dự kiến.

Khi **cả source và class** của cùng một kiểu đều tồn tại và cùng tham gia tìm kiếm, mặc định `javac` dùng bản có thời gian chỉnh sửa mới hơn (`-Xprefer:newer`). Tùy chọn nâng cao `-Xprefer:source` ưu tiên source. Trên môi trường CI, chỉ khác timestamp giữa hai máy cũng có thể khiến compiler chọn đầu vào khác nhau nếu để source/class chồng lấn. Đừng xem thời điểm sửa file là một cơ chế xác định dependency ổn định: tổ chức output riêng, kiểm soát classpath và dùng build sạch khi cần điều tra.

Lưu ý về Java module (JPMS): các bản dựng với `module-info.java` có thêm `--module-path`, `--module-source-path` và quy tắc module riêng. Ví dụ `-sourcepath src` ở đây minh họa dự án **không khai báo module**; không được áp công thức tìm kiếm classpath máy móc lên build nhiều module.

## 5. Biên dịch ngầm khác với biên dịch tăng dần

**Biên dịch ngầm (implicit source compilation)** là hành vi của compiler khi cần source phụ thuộc mà người gọi không nêu trực tiếp. **Biên dịch tăng dần (incremental compilation)** là chiến lược của công cụ build quyết định cần gọi compiler cho tập nguồn nào sau thay đổi. Hai cơ chế có liên quan nhưng không đồng nhất.

Ví dụ một project có `App.java` phụ thuộc `Greeting.java`. Nếu lệnh chỉ liệt kê `App.java`, chế độ `-implicit:class` có thể tạo cả `Greeting.class`, kể cả khi script không chủ đích liệt kê `Greeting.java`. Khi script chuyển sang `-implicit:none`, tập output có thể thiếu `Greeting.class`. Một lần chạy cũ còn class file trong output sẽ che lấp lỗi này; build sạch có thể thất bại ở runtime.

Các công cụ Gradle/Maven thường tự quản lý tập source, đường dẫn, compiler option, annotation processor và output. Không nên cho rằng chúng luôn gọi `javac` với đúng một source, cũng không nên bật `-implicit:none` toàn cục chỉ vì muốn “build nhanh hơn”. Việc tối ưu tăng dần cần dựa trên cơ chế và cấu hình plugin thực tế. Thay đổi tùy chọn `-implicit` có thể thay đổi tập artifact sinh ra nhưng **không thay thế cơ chế theo dõi dependency** của build tool.

Để so sánh đầu ra, hãy làm riêng ở các thư mục `out-class`, `out-none`, `out-explicit` rỗng như ví dụ. Đừng thực nghiệm chồng trên thư mục class của bản dựng đang được sử dụng.

## 6. Annotation processing: phạm vi cần thận trọng

Annotation processing có thể đọc khai báo và tạo thêm tệp nguồn qua các vòng xử lý. Tệp nguồn được compiler phát hiện **ngầm** có thể xuất hiện sau khi annotation processing đã chạy; khi không chỉ định `-implicit`, compiler có thể cảnh báo rằng source ấy được biên dịch mà không trải qua annotation processing như các source tường minh. Nếu khai báo `-implicit:class` hoặc `-implicit:none`, cảnh báo mặc định liên quan trường hợp này không còn xuất hiện chỉ vì thiếu giá trị `-implicit`.

Điểm cần phân biệt:

- `-implicit:none`: điều khiển **class file của nguồn tìm thấy ngầm**, không phải công tắc tắt annotation processing.
- `-proc:none`: tắt annotation processing.
- `-proc:only`: chạy annotation processing mà không thực hiện bước biên dịch bytecode tiếp theo.
- `-processor`, `-processorpath` hoặc `--processor-module-path`: chọn processor và đường dẫn tìm processor theo cơ chế tương ứng.

Nếu một annotation processor cần thấy annotation `SOURCE` trên các tệp phụ thuộc, chỉ dựa vào việc compiler tải ngầm source có thể không đủ. Cần đưa những source cần được xử lý vào compilation unit tường minh hoặc tổ chức build theo tài liệu của processor. **Đừng hiểu việc hết warning khi truyền `-implicit` là bảo đảm processor đã xử lý mọi tệp phụ thuộc.**

Từ JDK 23 trở đi, hành vi phát hiện/tự chạy annotation processor đã được siết chặt so với một số phiên bản cũ; vì vậy cần chỉ định cấu hình processor rõ ràng và kiểm chứng trên đúng JDK dự án. Điều này không làm thay đổi nghĩa chính của `-implicit:class` / `-implicit:none`.

## 7. Cách chẩn đoán kết quả biên dịch ngầm

Khi một source “tự nhiên được biên dịch” hoặc “compiler báo thành công nhưng thiếu class”, thực hiện lần lượt:

1. **Ghi lại lệnh `javac` đầy đủ.** Tách rõ danh sách `.java` được nêu trực tiếp, `-sourcepath`, `-classpath`, `-d`, `-implicit`, annotation processor và JDK đang dùng.
2. **Xác định kiểu bị thiếu hoặc sinh thêm.** Chẳng hạn `demo.Greeting` có `.java` trong source path, `.class` trong classpath hay cả hai?
3. **Kiểm tra output từ thư mục sạch.** Nếu `Greeting.class` đã tồn tại, không thể kết luận compiler của lần chạy hiện tại đã tạo nó.
4. **Quan sát `javac -verbose`.** Khi cần, thêm `-verbose` vào lệnh để xem các tệp được đọc, phân tích và ghi ra; nội dung log phụ thuộc JDK và môi trường, không dùng output verbose làm chuẩn kiểm thử bất biến.
5. **Thử so sánh `-implicit:class` và `-implicit:none`.** Chỉ đổi tùy chọn này giữa hai thử nghiệm có cùng source/classpath và output rỗng. So sánh file sinh ra, không chỉ so mã thoát 0.
6. **Thử liệt kê source tường minh.** Nếu chuyển `Greeting.java` từ source ngầm sang đầu vào tường minh làm xuất hiện `Greeting.class` ngay cả với `-implicit:none`, đã xác nhận đúng nguyên nhân.
7. **Kiểm tra runtime riêng.** `java -cp ...` cần thấy mọi class phụ thuộc tại thời điểm dùng; runtime classpath không được suy ra chỉ từ đường dẫn nguồn đã có lúc compile.

Một số triệu chứng:

| Triệu chứng | Điều cần kiểm tra |
| --- | --- |
| Thêm `-implicit:none` thì thiếu `Greeting.class` | `Greeting.java` chỉ được compiler tìm ngầm; cần biên dịch nó tường minh hoặc cung cấp `.class` |
| `javac` báo `cannot find symbol` cho `Greeting` | Source không nằm ở source path đúng package, class không ở classpath, hoặc đường dẫn/case sai |
| Máy A tạo thêm class, máy B không tạo | Khác classpath/sourcepath, file `.class` đã tồn tại, timestamp `.java`/`.class`, compiler/JDK hoặc cách gọi build |
| Compile pass nhưng `java` báo `NoClassDefFoundError` | Thiếu class tại runtime; kiểm tra output và runtime classpath, trong đó có tình huống `-implicit:none` |
| Có warning liên quan implicit compilation và annotation processing | Kiểm tra source đưa vào lệnh, lịch trình xử lý annotation và `-implicit`; đừng chỉ ẩn warning |
| Sửa `Greeting.java` làm `App.class`/output thay đổi dù lệnh chỉ chỉ định App | Compiler đã đọc source phụ thuộc; kiểm tra `-sourcepath`, `-Xprefer` và chế độ implicit |

## 8. Kịch bản thường gặp khi bảo trì dự án

**Dự án nhỏ, chạy `javac` trực tiếp.** Nếu muốn sự tiện lợi, có thể chấp nhận `-implicit:class` và đặt source path rõ ràng. Nhưng muốn kết quả runtime đầy đủ thì phải xác nhận các class cần thiết đã được sinh vào output hoặc có trên classpath. Tập phụ thuộc phát hiện ngầm không phải một manifest chính thức của bản dựng.

**Script CI muốn danh sách đầu vào tường minh.** Có thể dùng `-implicit:none` để tránh sinh class từ các source phát hiện ngầm, đồng thời cung cấp toàn bộ `.java` cần biên dịch trong danh sách tường minh hoặc class đã build ở dependency hợp lệ. `-implicit:none` **một mình không đảm bảo** script không phụ thuộc source ngoài danh sách; compiler vẫn có thể đọc các nguồn đó để kiểm tra kiểu. Muốn tránh nguồn ngoài ý muốn, cần giới hạn `-sourcepath` và `-classpath` thích hợp.

**Đã có output cũ.** Không nên dùng “biên dịch thành công” làm bằng chứng tính đầy đủ. Nếu compiler tìm thấy `Greeting.class` cũ hoặc runtime vô tình nhận được nó, lỗi thiếu artifact có thể chỉ xuất hiện sau khi dọn build hoặc đưa lên CI. Hãy tái hiện với một output mới và classpath được chỉ rõ.

**Dự án có annotation processor.** Tên source xuất hiện trong đường dẫn tìm kiếm không bảo đảm nó có cùng vòng xử lý annotation như source được liệt kê trực tiếp. Cần xác minh generated source và generated class được tạo đúng theo contract của processor; tránh tùy chỉnh `-implicit` nhằm xử lý triệu chứng mà không hiểu luồng compile.

## 9. Bài tập thực hành có đáp án

Dùng hai file `App.java` và `Greeting.java` ở mục 3, với ba thư mục output rỗng. Dự đoán kết quả rồi chạy từng lệnh:

1. `javac -sourcepath src -d out-class -implicit:class src/demo/App.java` — sẽ tạo **hai** file class: `App.class` và `Greeting.class`.
2. `javac -sourcepath src -d out-none -implicit:none src/demo/App.java` — sẽ tạo **một** file class: `App.class`. Thử chạy từ `out-none` để thấy lỗi runtime vì thiếu `Greeting`.
3. `javac -sourcepath src -d out-explicit -implicit:none src/demo/App.java src/demo/Greeting.java` — sẽ tạo **hai** file class; chạy được và in `Hello from Greeting`.

Câu hỏi mở rộng: nếu `Greeting.java` có lỗi cú pháp nhưng được `App.java` tham chiếu, liệu `-implicit:none` có “bỏ qua” lỗi không? **Không:** compiler phải đọc nguồn phụ thuộc để lấy khai báo kiểu; lỗi source có thể làm compile thất bại dù compiler không sinh `Greeting.class`. Vì vậy `-implicit:none` kiểm soát *output*, không phải *khả năng đọc source* hay *phạm vi xác minh kiểu*.

Một câu hỏi khác: tại sao `javac -implicit:none App.java Greeting.java` vẫn tạo `Greeting.class`? Vì `Greeting.java` là source **tường minh**, không thuộc nhóm “implicitly referenced source files” mà tùy chọn muốn kiểm soát.

## 10. Nguyên tắc áp dụng

Khi quan sát một bản dựng Java, luôn hỏi ba câu riêng: **(1) compiler được yêu cầu biên dịch trực tiếp những source nào; (2) compiler tìm thêm source/class nào để giải quyết kiểu; (3) những class file nào thực sự được ghi vào output?** `-sourcepath`/`-classpath` trả lời chủ yếu câu (2); `-implicit:class` và `-implicit:none` điều khiển một phần câu (3); danh sách input `.java` quyết định câu (1).

Với build cần kiểm soát và tái lập, hãy dùng toolchain, đường dẫn, source inputs và output sạch nhất quán; tránh dựa vào các file cũ hoặc timestamp. Đối với Gradle/Maven, kiểm tra cấu hình compiler của phiên bản plugin đang sử dụng trước khi thêm tùy chọn thủ công. Tài liệu tham khảo chuẩn: [`javac` trong JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html), các mục **`-implicit`**, **Additional Source Files** và **Searching for Module, Package and Type Declarations**.
