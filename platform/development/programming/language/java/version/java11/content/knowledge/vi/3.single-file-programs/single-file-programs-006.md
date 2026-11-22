# Chọn mức ngôn ngữ nguồn theo compiler đang dùng

## 1. Bối cảnh: chạy chương trình Java trực tiếp từ tệp nguồn

Từ **Java 11** (JEP 330), lệnh `java` có thể **biên dịch tệp nguồn trong bộ nhớ rồi chạy ngay** (*source-file mode*):

```bash
java Hello.java
```

Đây là cách chạy thuận tiện cho ví dụ, bài thực hành, công cụ dòng lệnh nhỏ và chương trình có tệp nguồn đầu vào. Với tệp `.java`, launcher tự nhận diện chế độ chạy nguồn. Bạn không cần gọi `javac` trước và thông thường không có tệp `.class` được xuất ra đĩa từ lần chạy trực tiếp này.

Tuy nhiên, **cú pháp và API được phép dùng phụ thuộc mức nguồn mà compiler của JDK đang chạy hỗ trợ**. Nếu để mặc định, launcher dùng mức ngôn ngữ của JDK hiện tại; nếu muốn kiểm tra hoặc giới hạn theo một bản Java cụ thể, hãy chỉ định `--source N`:

```bash
java --source 11 Hello.java
```

Mục tiêu bài học: biết xác định JDK đang thực sự được gọi, chọn `N` phù hợp, đọc lỗi khi mã dùng tính năng mới hơn, và phân biệt thao tác chạy trực tiếp với tạo sản phẩm biên dịch để phân phối.

## 2. `--source N` có nghĩa gì trong source-file mode?

Cú pháp tổng quát:

```text
java [các_tùy_chọn] --source N ĐườngDẫn/TênTệp.java [tham_số_chương_trình...]
```

- `java` là **launcher** có cơ chế gọi compiler tích hợp để biên dịch tệp nguồn trước khi chạy. Phiên bản launcher đang dùng là phiên bản được in bởi `java -version`.
- `--source N` chọn **phiên bản ngôn ngữ nguồn** để phân tích/biên dịch mã; trong **source-file mode**, nó còn khiến compiler sử dụng cơ chế tương đương `--release N` để **giới hạn API công khai theo JDK N**.
- `N` là **số phiên bản Java** (chẳng hạn `11`, `17`, `21`), không phải tên tệp, phiên bản hệ điều hành hoặc tham số của `main`.
- `N` **phải thuộc các mức phiên bản mà JDK hiện tại hỗ trợ**. Không thể chạy launcher Java 11 rồi đòi biên dịch cú pháp Java 17 bằng `--source 17`. Ngược lại, JDK mới hơn có thể bỏ hỗ trợ một số mức rất cũ; luôn kiểm tra trên JDK cụ thể.
- `ĐườngDẫn/TênTệp.java` là tệp nguồn sẽ được chạy; các đối số **sau tệp** được chuyển vào `main(String[] args)`. Tùy chọn của launcher như `--source` phải đứng **trước tệp**.

Lệnh `java --source 11 Hello.java` có thể được chạy bằng launcher JDK mới hơn 11, nếu JDK đó vẫn hỗ trợ mức 11. Nó **không biến runtime đang chạy thành JDK 11**: quá trình thực thi vẫn diễn ra trên JVM của lệnh `java` vừa gọi. Việc mã biên dịch theo API/mức nguồn 11 là kiểm tra tương thích tại thời điểm biên dịch; nếu sản phẩm phải chạy thực tế trên JDK 11, hãy kiểm thử trên môi trường JDK 11.

Khi bỏ `--source`:

```bash
java Hello.java
```

launcher chọn mặc định theo **phiên bản JDK đang chạy**, chứ không tự đọc dự định tương thích của dự án. Vì thế câu lệnh ngắn gọn này phù hợp với mã chỉ cần chạy trên JDK hiện tại, nhưng thiếu tính tường minh khi bài học hoặc dự án yêu cầu mức ngôn ngữ cụ thể.

## 3. Xác định compiler/launcher mà môi trường thực sự dùng

Mở terminal và chạy:

```bash
java -version
javac -version
javac --help
```

- `java -version`: cho biết launcher/JVM đang gọi. **Đây là lệnh quan trọng nhất khi dùng `java --source N ...`**, vì launcher này thực hiện biên dịch trong source-file mode.
- `javac -version`: cho biết compiler riêng dùng với `javac ...`; có thể khác bản `java` nếu cấu hình `PATH`/`JAVA_HOME` chưa nhất quán.
- `javac --help`: xem giá trị được hỗ trợ ở các tùy chọn `--source` và `--release` trên bộ công cụ hiện có. Các giá trị hợp lệ phụ thuộc phiên bản JDK, không nên ghi nhớ một danh sách cố định cho mọi máy.

Nếu có nhiều JDK được cài, kiểm tra đường dẫn thực thi: trong Windows PowerShell có thể dùng `Get-Command java` và `Get-Command javac`; trong Command Prompt dùng `where.exe java` / `where.exe javac`; trên Linux/macOS dùng `command -v java` / `command -v javac`. Khi cần độ chắc chắn, gọi trực tiếp đường dẫn tuyệt đối đến `bin/java` và `bin/javac` của JDK mong muốn.

**Không suy luận rằng `java` và `javac` luôn trỏ đến cùng JDK.** Ví dụ một terminal có thể dùng launcher Java 17 nhưng compiler lệnh `javac` của Java 21. Chọn `--source` cho **lệnh thực sự chạy**, không chỉ dựa trên JDK đang cài trong máy hoặc cấu hình IDE.

## 4. Quy trình chọn mức nguồn N

1. **Xác định yêu cầu tương thích.** Nếu bài thực hành cần sử dụng Java 11, chọn `11`; nếu chương trình được phép dùng tính năng Java 17, có thể chọn `17` với JDK hỗ trợ. Đừng tự tăng lên phiên bản cao nhất chỉ vì đã cài JDK mới.
2. **Kiểm tra JDK đang thực hiện lệnh.** Đối với `java --source`, kiểm tra `java -version`; khi dùng `javac --release`, kiểm tra `javac -version`.
3. **Đảm bảo mức N được hỗ trợ.** Compiler không thể hiểu cú pháp của phiên bản mới hơn chính nó, và có thể không còn hỗ trợ một mức quá cũ. Nếu mức yêu cầu không còn được hỗ trợ, hãy chọn JDK phù hợp với mức đó; không thay đổi yêu cầu tương thích một cách âm thầm.
4. **Kiểm tra cả cú pháp và API.** Một tệp có thể dùng cú pháp Java 11 nhưng vẫn gọi API chỉ xuất hiện ở Java 17. Với source-file mode, `--source 11` kiểm tra đồng thời giới hạn ngôn ngữ và API của Java 11.
5. **Chạy trên runtime dự kiến khi cần đảm bảo khả năng vận hành.** Mức nguồn thành công không thay thế kiểm thử về môi trường, thư viện, cấu hình và hành vi thực thi.

| Nhu cầu | Cách thường dùng | Ý nghĩa |
| --- | --- | --- |
| Thử nhanh tệp nguồn với khả năng của JDK hiện tại | `java Demo.java` | Dùng mức mặc định của launcher hiện tại. |
| Chạy tệp nguồn với ràng buộc Java 11 | `java --source 11 Demo.java` | Biên dịch trong bộ nhớ theo ngôn ngữ/API Java 11 rồi chạy bằng JVM của launcher đang dùng. |
| Chạy tệp nguồn với ràng buộc Java 17 | `java --source 17 Demo.java` | Cần JDK hỗ trợ mức 17; cho phép tính năng/API Java 17. |
| Xuất `.class` tương thích Java 11 để dùng về sau | `javac --release 11 Demo.java` | Biên dịch ra tệp `.class` với ngôn ngữ, API và đích bytecode của Java 11. |
| Chạy lớp đã được biên dịch | `java Demo` | Chạy lớp `Demo` trên classpath, **không** chọn source-file mode. |

## 5. Ví dụ hoàn chỉnh: chạy một tệp nguồn theo Java 11

Tạo tệp **`SourceChoiceDemo.java`** với nội dung:

```java
public class SourceChoiceDemo {
    public static void main(String[] args) {
        var word = "Java";
        System.out.println(word.repeat(2));
        System.out.println("args=" + args.length);
    }
}
```

Chương trình sử dụng `var` cho biến cục bộ (hợp lệ từ Java 10) và `String.repeat(int)` (có từ Java 11), do đó phù hợp với mức **Java 11**. `args` nhận các tham số được đặt sau tên tệp nguồn.

Chạy trực tiếp bằng một JDK có hỗ trợ mức nguồn 11:

```bash
java --source 11 SourceChoiceDemo.java one two
```

**Kết quả chuẩn:**

```text
JavaJava
args=2
```

Giải thích:
- `--source 11` yêu cầu compiler sử dụng nguồn và API Java 11.
- `SourceChoiceDemo.java` là tệp để launcher biên dịch trong bộ nhớ và chạy.
- `one` và `two` là hai đối số truyền cho `main`; vì thế `args.length` bằng `2`.
- Mã chạy được từ tệp nguồn trực tiếp; không có bước `javac` thủ công.

Có thể chạy `java SourceChoiceDemo.java one two` nếu muốn dùng khả năng mặc định của JDK hiện tại, nhưng lệnh đó **không khẳng định** mã tương thích với Java 11.

Nếu muốn lưu class file để chạy lại, biên dịch riêng:

```bash
javac --release 11 SourceChoiceDemo.java
java SourceChoiceDemo one two
```

Hai lệnh trên xuất `SourceChoiceDemo.class` rồi chạy lớp đã biên dịch. Khi chạy trong thư mục khác, cần cấu hình classpath (ví dụ `java -cp out SourceChoiceDemo` nếu đã biên dịch với `javac -d out ...`). Với trường hợp tối giản cùng thư mục, không cần `-cp` tường minh. Đầu ra chương trình vẫn là hai dòng trên. Muốn kiểm tra chạy thật trên Java 11, hãy dùng JVM Java 11 trong môi trường kiểm thử.

## 6. Nếu chọn mức nguồn thấp hơn mã đang dùng

Compiler có **hai nhóm điều kiện** cần thỏa: cú pháp ngôn ngữ của phiên bản đã chọn, và những API công khai có ở phiên bản đó. Chúng có thể gây lỗi khác nhau.

### 6.1. Cú pháp ngôn ngữ mới hơn không được chấp nhận

Tạo tệp **`SwitchDemo.java`**:

```java
public class SwitchDemo {
    public static void main(String[] args) {
        int day = 2;
        String label = switch (day) {
            case 1 -> "Mon";
            case 2 -> "Tue";
            default -> "Other";
        };
        System.out.println(label);
    }
}
```

*Switch expression* theo hình thức trên là tính năng ngôn ngữ ổn định từ **Java 14**, nên Java 11 không hiểu cú pháp này. Trên JDK hỗ trợ mức 17, lệnh sau chạy thành công:

```bash
java --source 17 SwitchDemo.java
```

Kết quả:

```text
Tue
```

Nhưng:

```bash
java --source 11 SwitchDemo.java
```

sẽ **lỗi biên dịch**, với nội dung tương tự `switch expressions are not supported in -source 11`; thông báo chính xác có thể thay đổi theo JDK. Đây không phải lỗi khi thực thi `switch`; chương trình bị từ chối **trước khi chạy**. Nếu mục tiêu vẫn là Java 11, phải viết lại bằng cú pháp Java 11, chẳng hạn `switch` dạng câu lệnh truyền thống; nếu chấp nhận Java 17, chọn mức 17 và JDK tương ứng.

### 6.2. Cú pháp hợp lệ nhưng API chưa tồn tại ở mức đã chọn

Tạo tệp **`ApiDemo.java`**:

```java
public class ApiDemo {
    public static void main(String[] args) {
        byte[] bytes = {10, 11};
        System.out.println(
            java.util.HexFormat.of().formatHex(bytes)
        );
    }
}
```

`java.util.HexFormat` là API xuất hiện ở **Java 17**. Trên JDK hỗ trợ mức 17:

```bash
java --source 17 ApiDemo.java
```

Kết quả:

```text
0a0b
```

Nhưng `java --source 11 ApiDemo.java` sẽ từ chối biên dịch vì không tìm thấy kiểu `java.util.HexFormat` trong bộ API của Java 11. Dù trình biên dịch thực tế nằm trong JDK mới hơn, source-file mode với `--source 11` vẫn giới hạn API theo mức 11.

Đây là lý do không nên chỉ kiểm tra xem code có dùng `var`, lambda hay `switch` đời mới hay không. **Khả năng tương thích còn phụ thuộc thư viện Java SE/JDK mà chương trình gọi.**

## 7. Phân biệt `java --source`, `javac --source` và `javac --release`

Từ `--source` xuất hiện trong hai lệnh, nhưng **không được hiểu chúng là cùng một quy trình**:

| Lệnh | Phạm vi điều khiển | Kết quả |
| --- | --- | --- |
| `java --source 11 Demo.java` | Source-file mode: chọn nguồn 11; compiler ngầm áp dụng các hạn chế tương đương `--release 11` trong bước biên dịch nguồn. | Biên dịch trong bộ nhớ và chạy ngay bằng JVM hiện có. |
| `javac --source 11 Demo.java` | Chọn **quy tắc cú pháp** Java 11 cho compiler `javac`. | Tạo `.class`; **chỉ `--source` không đủ để cam kết** API và bytecode tương thích Java 11. |
| `javac --release 11 Demo.java` | Chọn cú pháp, phiên bản API và đích bytecode của Java 11. | Tạo `.class` phù hợp mục tiêu phát hành Java 11. |
| `javac Demo.java` | Dùng mặc định của `javac` hiện tại. | Tạo `.class` theo mặc định của compiler hiện tại. |
| `java Demo` | Chạy lớp đã biên dịch có tên `Demo`. | Không biên dịch `Demo.java` theo source-file mode. |

Đối với công việc **phát hành phần mềm chạy trên JDK cũ hơn JDK biên dịch**, ưu tiên `javac --release N` hoặc cấu hình tương đương trong Maven/Gradle. Chỉ `-source N -target N` có thể không giới hạn đúng API của bản Java đích; `--release` tránh vấn đề này.

Đối với **chạy nhanh tệp nguồn**, dùng `java --source N file.java`. Dù chữ `--source` giống nhau, ở đây launcher tự thực hiện biên dịch theo release tương ứng. Không lấy sự khác biệt ở `javac` để suy ra rằng `java --source 11` vẫn thoải mái dùng API mới của JDK hiện tại.

## 8. Tương thích không đồng nghĩa với đổi phiên bản JVM

Giả sử máy đang dùng **launcher Java 21**, mã ví dụ Java 11 có thể chạy bằng `java --source 11 SourceChoiceDemo.java`. Khi đó:

- Compiler chạy ở chế độ chấp nhận cú pháp/API Java 11 trong bước biên dịch nguồn.
- JVM thực thi vẫn là **Java 21**, vì `--source` không cài, tải hoặc chuyển launcher sang Java 11.
- Việc chạy thành công trên JVM 21 **không chứng minh độc lập** ứng dụng vận hành đúng trên JVM 11 với toàn bộ môi trường của nó.
- Với tệp `.class` được tạo bằng `javac --release 11`, bytecode được thiết kế cho đích Java 11; tuy nhiên vẫn cần xem xét thư viện phụ thuộc, cấu hình và kiểm thử thực tế.

Nếu dùng launcher Java 11 và cần cú pháp của Java 17, `--source 17` không thể nâng cấp compiler. Hãy sử dụng một JDK đủ mới rồi lựa chọn mức nguồn tương ứng. Nếu quy định tương thích bắt buộc là Java 11, thay vì tăng `N` để qua lỗi cú pháp/API, hãy sửa mã về những khả năng có sẵn ở Java 11.

## 9. Cách đặt tham số lệnh và lỗi thường gặp

### Tùy chọn launcher phải nằm trước tên tệp

**Đúng:**

```bash
java --source 11 SourceChoiceDemo.java one two
```

**Sai về mục đích chọn nguồn:**

```bash
java SourceChoiceDemo.java --source 11
```

Ở lệnh thứ hai, phần `--source` và `11` đứng **sau tên tệp**, nên được đưa cho `main(String[] args)` như đối số chương trình; chúng **không thiết lập** mức nguồn. Với ví dụ `SourceChoiceDemo`, chương trình vẫn thấy hai đối số và in `args=2`, điều này dễ đánh lừa người mới.

### Phân biệt đường dẫn tệp với tên lớp

`java Demo.java` là source-file mode; `java Demo` tìm lớp đã biên dịch `Demo`. Nếu chưa có `Demo.class` (hoặc classpath không đúng), lệnh `java Demo` có thể báo không tìm thấy lớp chính. Hãy quyết định rõ bạn muốn **chạy nguồn** hay **chạy lớp**.

Với tệp không có đuôi `.java`, dạng `java --source N ten-script` cũng có thể kích hoạt source-file mode, miễn `ten-script` là tệp nguồn hợp lệ và JDK hỗ trợ mức `N`. Đây là tình huống dùng tệp nguồn như một script; không cần đổi tên tệp trong những trường hợp thông thường chỉ để học `--source`.

### Đọc thông báo lỗi để chọn hướng xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Mức `N` bị báo không hỗ trợ | `N` cao hơn hoặc đã nằm ngoài danh sách phiên bản mà compiler hiện tại hỗ trợ. | Kiểm tra `java -version`, `javac --help`; dùng JDK có hỗ trợ mức yêu cầu. |
| `switch expressions are not supported in -source 11` | Mã dùng cú pháp mới hơn Java 11. | Viết lại bằng cú pháp Java 11 hoặc nâng mức nguồn/điều kiện môi trường nếu được phép. |
| `cannot find symbol: HexFormat` khi chọn 11 | API Java 17 không thuộc API Java 11. | Chọn API thay thế có ở Java 11 hoặc thay đổi yêu cầu phiên bản một cách có chủ đích. |
| `Could not find or load main class Demo` | Gọi `java Demo` khi chưa có class đúng tên/classpath. | Dùng `java Demo.java` để chạy nguồn hoặc biên dịch rồi dùng `java Demo`. |
| `java -version` và `javac -version` khác nhau | `PATH`/`JAVA_HOME`/cấu hình terminal trỏ đến các JDK khác nhau. | Xác định đường dẫn lệnh thực tế và dùng JDK mong muốn. |
| Chạy được trên JDK mới nhưng không chạy trên JDK đích | Chưa đảm bảo API, bytecode, thư viện hoặc môi trường runtime tương ứng. | Dùng `javac --release N` khi build và kiểm thử trên JDK đích. |

Không gán cho `--source` nhiệm vụ tự quản lý dependency, classpath, đóng gói JAR hay cấu hình dự án. Nếu bài toán cần build phát hành hay nhiều module, dùng quy trình build thích hợp; `java --source` chủ yếu giúp vận hành và kiểm thử nhanh mã nguồn theo mức đã chọn.

## 10. Bài tập tự kiểm tra

**Tình huống A.** Bạn đang dùng launcher Java 21 nhưng bài tập phải tuân thủ Java 11. Nên chạy như thế nào?

```bash
java --source 11 SourceChoiceDemo.java
```

Giải thích: bạn yêu cầu mức ngôn ngữ/API Java 11 trong bước biên dịch nguồn. JVM chạy vẫn là Java 21; nếu cần chứng minh chạy trên Java 11, hãy kiểm thử riêng với runtime Java 11.

**Tình huống B.** Bạn muốn viết một công cụ Java 17 dùng `HexFormat` và đang dùng launcher Java 11. Chỉ thêm `--source 17` có đủ không?

**Không.** Compiler của JDK 11 không hỗ trợ mức Java 17. Cần JDK hỗ trợ Java 17; nếu yêu cầu Java 11 là bắt buộc thì phải chọn API đã có từ Java 11.

**Tình huống C.** Đoạn `ApiDemo.java` không dùng cú pháp mới hơn Java 11. Tại sao `java --source 11 ApiDemo.java` vẫn lỗi?

Vì ngoài cú pháp, `--source 11` trong source-file mode giới hạn **API** theo Java 11. `HexFormat` không nằm trong Java 11.

**Tình huống D.** Bạn cần tạo file `.class` để ứng dụng chạy trên Java 11. Chọn `java --source 11` hay `javac --release 11`?

Chọn **`javac --release 11`** để tạo bytecode và kiểm soát cú pháp/API của Java 11; tiếp tục kiểm thử trên runtime thực tế khi cần. `java --source 11` là lệnh biên dịch trong bộ nhớ và chạy ngay, không phải bước đóng gói.

**Tình huống E.** Chạy `java SourceChoiceDemo.java --source 11`, chương trình báo có hai đối số. Tại sao mức nguồn không đổi?

Vì mọi token sau tên tệp nguồn được chuyển vào `main`, nên `--source 11` đã trở thành hai đối số chương trình. Cần đặt trước tên tệp.

## 11. Ghi nhớ và tài liệu chính thức

- `java Hello.java`: chạy mã nguồn trực tiếp; mặc định theo JDK thực hiện lệnh.
- `java --source N Hello.java`: ép mức ngôn ngữ/API trong source-file mode, với `N` thuộc phạm vi hỗ trợ của JDK đang chạy.
- `javac --release N Hello.java`: tạo class file tương thích phiên bản mục tiêu, bao gồm cả giới hạn API, cú pháp và bytecode.
- `java Hello`: chạy lớp đã biên dịch. `--source` không chọn JVM có phiên bản `N`.
- Muốn biết phiên bản thực tế: xem `java -version`, `javac -version`; muốn biết mức hỗ trợ: đọc `javac --help` của JDK đó.

Tài liệu có hiệu lực cho cách sử dụng Java hiện đại:
- [OpenJDK JEP 330 — Launch Single-File Source-Code Programs](https://openjdk.org/jeps/330).
- [Oracle Java launcher — Using Source-File Mode to Launch Source-Code Programs](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html).
- [Oracle `javac` command — `--source`, `--release` và `--target`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html).