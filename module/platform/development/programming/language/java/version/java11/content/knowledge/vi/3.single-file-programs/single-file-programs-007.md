# Shebang trên hệ điều hành hỗ trợ (Java 11+)

## 1. Shebang là gì và liên quan thế nào đến Java 11?

**Shebang** là dòng đầu tiên bắt đầu bằng `#!` trong một tệp thực thi dạng văn bản trên hệ điều hành hỗ trợ cơ chế này, phổ biến ở Linux, macOS và các hệ Unix-like. Hệ điều hành đọc dòng đó để xác định **chương trình thông dịch/chạy tệp** khi người dùng gọi trực tiếp `./ten-script`.

Từ **Java 11**, JEP 330 (*Launch Single-File Source-Code Programs*) bổ sung khả năng đưa Java launcher vào cơ chế này: một tệp chứa mã nguồn Java có thể được chạy như script bằng đường dẫn tệp, ví dụ `./greet`, **không cần gọi `javac` trước**. Đây vẫn là khả năng được hỗ trợ trong Java hiện đại.

Ví dụ về dòng đầu tệp:

~~~text
#!/usr/bin/java --source 11
~~~

Trong đó:

- `#!`: dấu hiệu shebang phải nằm ở **đầu dòng đầu tiên**.
- `/usr/bin/java`: đường dẫn tuyệt đối đến Java launcher **thực sự có trên máy**; chỉ là một ví dụ, không phải đường dẫn chung cho mọi máy.
- `--source 11`: yêu cầu Java chạy ở chế độ **source-file** với mức ngôn ngữ/API Java 11. Phiên bản đang cài phải hỗ trợ mức nguồn này.

**Phân biệt hai vai trò:** hệ điều hành sử dụng shebang để quyết định gọi `java`; Java launcher sau đó đọc mã nguồn, bỏ qua dòng shebang theo quy tắc của source-file mode, biên dịch trong bộ nhớ và chạy chương trình. Shebang **không phải cú pháp Java** và Java cũng **không trở thành trình thông dịch Bash**.

## 2. Điều kiện để chạy được

Để chạy trực tiếp `./greet` theo ví dụ dưới đây, cần thỏa mãn đủ các điều kiện:

1. **Hệ điều hành hỗ trợ shebang**, như Linux/macOS/Unix-like; Windows thông thường không có cơ chế `#!` tương đương khi chạy `.\greet` từ Command Prompt hoặc PowerShell.
2. Có **JDK/Java launcher phiên bản 11 trở lên** với tùy chọn `--source` và mức nguồn được chọn vẫn được phiên bản JDK đó hỗ trợ.
3. Dòng đầu tệp thật sự bắt đầu bằng hai ký tự `#!`, trỏ đến một Java launcher có thể thực thi. Không được đặt dòng trống, BOM (dấu đánh dấu mã hóa) hay ký tự khác trước `#!`.
4. **Tên tệp chứa shebang không kết thúc bằng `.java`**. Có thể dùng tên không phần mở rộng như `greet`. Đây là quy tắc quan trọng vì Java chỉ bỏ qua dòng shebang khi tệp được chạy dưới dạng script **không có đuôi `.java`**.
5. Tệp được cấp quyền chạy trên Unix-like bằng `chmod +x`, nằm trên hệ thống tệp cho phép thực thi và được gọi bằng đúng đường dẫn, ví dụ `./greet`.
6. Tệp được lưu với mã hóa văn bản tương thích; với script dùng trên Unix, nên dùng **UTF-8 không BOM và kết thúc dòng LF** để tránh lỗi xác định trình thông dịch.

Có thể kiểm tra Java launcher hiện có bằng:

~~~bash
command -v java
java --version
~~~

Nếu `command -v java` trả về `/usr/bin/java` thì ví dụ dưới dùng được nguyên dạng. Nếu trả về đường dẫn khác, thay `/usr/bin/java` trên dòng shebang bằng **đường dẫn tuyệt đối đúng** tới launcher có thể chạy trên máy, đồng thời kiểm tra phiên bản Java. Trên một số máy, `java` là symlink tới thư mục JDK, nhưng shebang chỉ cần trỏ tới đường dẫn thực thi hợp lệ.

## 3. Ví dụ hoàn chỉnh: tệp `greet` chạy như lệnh Unix

Tạo **một tệp tên chính xác là `greet` (không có đuôi `.java`)** với nội dung sau:

~~~java
#!/usr/bin/java --source 11
public class Greet {
    public static void main(String[] args) {
        String name = args.length == 0 ? "guest" : args[0];
        System.out.println("Hello, " + name + "!");
    }
}
~~~

Lưu ý khi chép ví dụ: phần `#!/usr/bin/java --source 11` phải là **dòng đầu tiên của tệp**. Khối Markdown ghi ngôn ngữ `java` để dễ đọc mã, nhưng dòng `#!` chỉ hợp lệ **trong ngữ cảnh shebang của source-file mode**, không phải khai báo Java bình thường.

Trong terminal Linux/macOS, từ thư mục có tệp:

~~~bash
chmod +x greet
./greet Minh
./greet
./greet "Ngoc Anh"
~~~

Kết quả chuẩn tương ứng:

~~~text
Hello, Minh!
Hello, guest!
Hello, Ngoc Anh!
~~~

**Giải thích từng bước:**

1. `chmod +x greet` bổ sung quyền thực thi cho tệp.
2. Khi chạy `./greet Minh`, hệ điều hành nhận diện `#!` và gọi Java launcher được chỉ định trên dòng đầu; `greet` là tệp mã nguồn đầu vào và `Minh` là đối số chương trình.
3. `--source 11` hướng Java launcher sang chế độ chạy tệp nguồn, mặc dù tên tệp không có `.java`.
4. Java launcher bỏ qua dòng shebang, xử lý/biên dịch mã nguồn Java trong bộ nhớ rồi gọi `public static void main(String[] args)` của lớp `Greet`.
5. `args[0]` nhận `Minh`, `"Ngoc Anh"` hoặc không có phần tử nào tùy lệnh gọi. Toán tử điều kiện `args.length == 0 ? "guest" : args[0]` tránh lỗi truy cập phần tử khi không truyền đối số.

Tên **lớp `Greet` không bắt buộc giống tên tệp script `greet`** trong source-file mode. Tệp có thể không mang phần mở rộng; điều thiết yếu là lớp được chọn để chạy có phương thức `main` phù hợp. Với mã Java 11 như ví dụ, cách viết `public static void main(String[] args)` vẫn là lựa chọn rõ ràng và tương thích.

Ví dụ này **đã được kiểm tra bằng lệnh `java --source 11` với một tệp không có đuôi `.java`**: hai trường hợp `Minh` và không truyền đối số lần lượt in đúng `Hello, Minh!` và `Hello, guest!`. Thao tác `chmod` và gọi `./greet` chỉ áp dụng trên hệ điều hành Unix-like có hỗ trợ shebang.

## 4. Vì sao phải đặt `--source` và bỏ đuôi `.java`?

Khi chạy một tệp `Hello.java` bình thường, Java launcher có thể tự nhận biết chế độ chạy nguồn qua phần mở rộng:

~~~bash
java Hello.java
~~~

Với script tên `greet`, không có `.java` để kích hoạt chế độ đó. Vì vậy phải có `--source <N>` trước tên tệp:

~~~bash
java --source 11 greet Minh
~~~

Câu lệnh trên là cách **gọi trực tiếp Java launcher** để thử nghiệm hoặc chẩn đoán, không yêu cầu Unix thực thi shebang. Java nhận biết tên tệp không kết thúc bằng `.java` và nếu dòng đầu bắt đầu bằng `#!` thì **bỏ qua dòng đầu đó** khi biên dịch.

Ngược lại, cách sau **không hợp lệ**:

~~~text
Tên tệp: greet.java
Dòng 1:  #!/usr/bin/java --source 11
~~~

Vì tệp kết thúc bằng `.java`, Java xử lý nội dung như mã nguồn Java thông thường. Dòng `#!` lúc này tạo lỗi cú pháp (chẳng hạn `illegal character: '#'`). **Chỉ đổi quyền bằng `chmod +x` không sửa được lỗi này.** Để dùng shebang, đổi tên tệp sang `greet`; để dùng `greet.java`, bỏ dòng shebang và chạy `java greet.java` nếu mã nguồn có lớp phù hợp.

Bảng đối chiếu:

| Tệp | Dòng đầu | Cách chạy | Kết luận |
| --- | --- | --- | --- |
| `greet` | `#!/usr/bin/java --source 11` | `chmod +x greet` rồi `./greet` | Đúng trên Unix-like có Java đúng đường dẫn |
| `greet` | `#!/usr/bin/java --source 11` | `java --source 11 greet` | Đúng khi gọi launcher trực tiếp |
| `Greet.java` | `public class Greet { ... }` | `java Greet.java` | Đúng: source-file mode, không dùng shebang |
| `greet.java` | `#!/usr/bin/java --source 11` | `./greet.java` hoặc `java greet.java` | Sai: Java không bỏ qua shebang của tệp `.java` |
| `greet` | Mã Java bình thường, không shebang | `./greet` | Sai: hệ điều hành không biết phải dùng Java; hãy dùng `java --source 11 greet` |

Các bảng trên giả định mã Java bên trong hợp lệ và JDK hỗ trợ mức `--source 11`.

## 5. Hiểu luồng khởi chạy: không có bước `javac` riêng

~~~text
Người dùng: ./greet Minh
            |
            v
Hệ điều hành Unix-like đọc dòng #! của tệp greet
            |
            v
Gọi Java launcher: /usr/bin/java --source 11 greet Minh
            |
            v
Java launcher đọc tệp greet, bỏ qua shebang
            |
            v
Biên dịch mã nguồn vào bộ nhớ và nạp lớp
            |
            v
Chạy Greet.main(new String[] { "Minh" })
            |
            v
stdout: Hello, Minh!
~~~

Sơ đồ thể hiện **ý nghĩa logic** của việc khởi chạy; cách hệ điều hành đóng gói đối số shebang phụ thuộc nền tảng và Java launcher xử lý cú pháp hỗ trợ. Không dùng sơ đồ để suy ra rằng Bash hay kernel tự biên dịch Java.

Cơ chế này đặc biệt hữu ích cho script nhỏ và tiện ích nội bộ vì không phải tạo thủ công `.class` hay `.jar`. **Không có tệp `Greet.class` được tạo trên ổ đĩa chỉ bởi lệnh chạy source-file mode**; launcher biên dịch và nạp mã nguồn trong quá trình chạy. Khi chạy lại, mã nguồn vẫn phải được xử lý; đây không phải cơ chế đóng gói tối ưu cho ứng dụng lớn.

Nếu có lỗi biên dịch, chương trình không bắt đầu thực thi `main`, thông báo được ghi ra stderr và launcher trả mã thoát khác 0. Nếu lỗi xảy ra trong `main`, đó là lỗi chạy chương trình Java bình thường, không phải lỗi của bản thân shebang.

## 6. Chọn đúng Java khi đường dẫn cài đặt khác nhau

**Cách đơn giản và dễ dự đoán:** dùng đường dẫn tuyệt đối của Java launcher trong shebang. Ví dụ đường dẫn sau chỉ mang tính minh họa và cần thay bằng đường dẫn cài đặt thực:

~~~text
#!/opt/jdk-21/bin/java --source 11
~~~

Ở đây JDK 21 có thể chạy mã nguồn tương thích Java 11, miễn mức nguồn được hỗ trợ. Trước khi triển khai hãy kiểm tra `/opt/jdk-21/bin/java` tồn tại và có quyền thực thi.

Trên một số hệ Unix có lệnh `env` hỗ trợ tùy chọn tách đối số `-S`, bạn cũng có thể dùng:

~~~text
#!/usr/bin/env -S java --source 11
~~~

Cách này tra cứu `java` theo biến môi trường `PATH` thay vì ghim đường dẫn JDK. **Chỉ sử dụng khi `/usr/bin/env` của hệ điều hành thực sự hỗ trợ `-S`**, và khi `PATH` trong môi trường khởi chạy chọn đúng phiên bản Java. Một số hệ thống hoặc công cụ `env` không có tùy chọn này.

Không nên tùy tiện thay bằng:

~~~text
#!/usr/bin/env java --source 11
~~~

Cách đó có thể bị hệ điều hành chuyển nguyên chuỗi `java --source 11` thành **một đối số** cho `env`, dẫn tới `env` không tìm thấy lệnh cần chạy. Cú pháp shebang không có quy tắc tách đối số hoàn toàn giống shell; dùng đường dẫn Java tuyệt đối hoặc `env -S` khi đã xác minh hỗ trợ.

**Quy tắc thực hành:** Khi tài liệu, script và máy chạy thuộc cùng một môi trường được kiểm soát, shebang với đường dẫn Java tuyệt đối thường dễ kiểm tra và gỡ lỗi nhất. Khi script cần chạy nhiều máy, hãy mô tả rõ yêu cầu về `env -S`, `PATH` và phiên bản JDK thay vì giả định mọi hệ Unix giống nhau.

## 7. Truyền đối số và dùng khi chạy tác vụ

Các đối số đặt **sau tên tệp script** đi vào mảng `String[] args` của phương thức `main`.

~~~bash
./greet Minh
./greet "Ngoc Anh"
./greet
~~~

Dấu nháy đôi trong lệnh thứ hai khiến shell truyền `Ngoc Anh` thành **một đối số** (với dấu cách bên trong); chúng không trở thành phần dữ liệu trong `args[0]`. Không có đối số thì `args.length == 0`.

Khi gọi Java launcher trực tiếp, nguyên tắc vẫn vậy:

~~~bash
java --source 11 greet Minh
~~~

`--source 11` là **tùy chọn của Java launcher**. `greet` là **tên tệp nguồn**. `Minh` là **đối số gửi đến chương trình**. Nếu đặt `Minh` trước `greet` hoặc `--source` sau tên script, Java launcher không hiểu vị trí đó như trường hợp mong muốn.

Dùng dạng này cho script nhỏ như đọc tham số, kiểm tra dữ liệu, hiển thị thông tin hoặc tự động hóa tác vụ đơn giản. Nếu cần chương trình nhiều thành phần, build lặp lại, test/đóng gói và phân phối, sử dụng cách tổ chức project/build tool phù hợp. Trong phạm vi bài này, chỉ cần **một tệp mã nguồn làm điểm vào**; các JDK mới đã mở rộng một số khả năng chạy nguồn nhưng không thay đổi nguyên lý shebang cốt lõi của Java 11.

## 8. Lỗi thường gặp và cách xử lý

| Hiện tượng/lỗi điển hình | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `Permission denied` khi `./greet` | Chưa cấp quyền thực thi hoặc hệ thống tệp cấm chạy | `chmod +x greet`; kiểm tra quyền và tùy chọn mount |
| `No such file or directory` / `bad interpreter` | Đường dẫn Java trong shebang không tồn tại hoặc không thực thi được | Kiểm tra `command -v java`; cập nhật dòng `#!` theo đường dẫn thật |
| `bad interpreter ... ^M` | Tệp dùng kết thúc dòng CRLF trên môi trường cần LF | Chuyển dòng sang LF và lưu lại |
| `illegal character: '#'` | Dòng shebang được đưa vào trình biên dịch như mã Java, thường do dùng tên `.java` | Bỏ đuôi `.java` của tệp shebang; hoặc bỏ shebang nếu dùng `.java` |
| `env: ... No such file or directory` | `env` không tách đúng phần `java --source ...` hoặc `PATH` sai | Dùng đường dẫn tuyệt đối hoặc `env -S` khi có hỗ trợ |
| `Unrecognized option` / `invalid source release` | JDK đang chạy không hỗ trợ tùy chọn/mức nguồn đã ghi | Kiểm tra `java --version` và `java --help`; chọn JDK/mức nguồn được hỗ trợ |
| Java báo lỗi phương thức `main` | Lớp đầu vào không có entry point hợp lệ với mức Java chọn | Với Java 11, định nghĩa `public static void main(String[] args)` trong lớp cần chạy |
| `No such file` khi gõ `greet` | Thư mục hiện tại không nằm trong `PATH` | Gọi `./greet` hoặc đường dẫn tới script |
| Script chạy được qua `java --source 11 greet` nhưng không chạy được qua `./greet` | Phần Java hợp lệ, vấn đề nằm ở shebang, quyền hoặc hệ điều hành | Kiểm tra đúng dòng đầu, đường dẫn interpreter, LF và quyền chạy |

Một số hệ điều hành hiển thị thông báo lỗi khác nhau cho cùng nguyên nhân. Dùng cặp lệnh dưới đây để tách lỗi ở **tầng hệ điều hành** khỏi lỗi ở **tầng Java launcher**:

~~~bash
java --source 11 greet Minh
./greet Minh
~~~

Nếu lệnh đầu chạy đúng còn lệnh thứ hai lỗi, ưu tiên kiểm tra `#!`, đường dẫn tuyệt đối, quyền thực thi, xuống dòng LF và hỗ trợ shebang của hệ điều hành.

### Những điều cần tránh

- **Không đặt shebang ở dòng thứ hai** hoặc trước nó có BOM/khoảng trắng. Hệ điều hành có thể không nhận diện script.
- **Không đặt lệnh Bash vào phần thân mã nguồn Java**. Trừ dòng `#!` được xử lý đặc biệt, nội dung còn lại vẫn phải là mã Java hợp lệ.
- **Không gắn `.java` cho tệp có shebang** rồi kỳ vọng Java tự bỏ qua dòng `#!`.
- **Không nhầm `--source 11` với “dùng đúng JDK 11”**. Nó chọn mức ngôn ngữ/API được JDK đang chạy hỗ trợ; chính đường dẫn tới `java` quyết định Java launcher/runtime được sử dụng.
- **Không cho rằng mọi JDK tương lai sẽ vĩnh viễn hỗ trợ `--source 11`**. Danh sách mức nguồn cũ có thể thay đổi theo phiên bản JDK; kiểm tra công cụ trên máy thực tế.
- **Không cho rằng Windows có thể trực tiếp chạy `./greet` nhờ shebang**. Trên Windows, cách sử dụng chính là gọi Java launcher tường minh khi cần thử source-file mode.

## 9. Khi nào nên dùng và checklist cuối

Shebang với Java phù hợp khi muốn biến một đoạn Java ngắn thành lệnh dòng lệnh quen thuộc trên Unix-like, đặc biệt khi cả nhóm đã dùng Java và máy chạy có JDK. Để nội dung dễ bảo trì, hãy luôn lưu tài liệu về phiên bản Java, đường dẫn launcher hoặc chính sách dùng `env -S`.

**Checklist trước khi chạy:**

1. Tệp script tên `greet`, **không** phải `greet.java`.
2. Hai byte đầu là `#!`, không có BOM; dòng đầu chỉ rõ Java launcher và `--source N`.
3. JDK thực tế chạy được phiên bản nguồn `N` đã chọn.
4. Tệp là mã nguồn Java hợp lệ với entry point phù hợp (Java 11: `public static void main(String[] args)`).
5. Trên Unix-like: quyền thực thi đã bật, dòng kết thúc kiểu LF, launcher tồn tại.
6. Gọi bằng `./greet`, truyền đối số phía sau, kiểm tra stdout và mã thoát.
7. Nếu có lỗi, thử `java --source 11 greet` để phân biệt lỗi Java với lỗi shebang.

**Ghi nhớ:** Java 11 không biến Java thành ngôn ngữ shell. Shebang giúp **hệ điều hành chọn Java launcher**; `--source` cho phép **Java chạy một tệp nguồn như script**. Hai cơ chế phối hợp tạo trải nghiệm gọi chương trình bằng `./ten-script` trên hệ điều hành hỗ trợ, và vẫn là kiến thức hữu ích trên các JDK hiện đại.

## Tài liệu tham khảo

- [JEP 330 — Launch Single-File Source-Code Programs](https://openjdk.org/jeps/330): đặc tả tính năng được đưa vào Java 11, bao gồm shebang và source-file mode.
- [OpenJDK/Dev.java — Launching Simple Source-Code Programs](https://dev.java/learn/first-steps/first-java-code/launch-simple-source-code-programs/): hướng dẫn hiện hành và ví dụ chạy tệp nguồn như shebang.
- [Oracle Java Command Reference, Java SE 25 — Source-File Mode](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#using-source-file-mode-to-launch-source-code-programs): chế độ chạy nguồn, `--source`, chọn lớp chạy và truyền đối số.
- [JetBrains IntelliJ IDEA — Run shebang scripts](https://www.jetbrains.com/help/idea/shebang-scripts.html): cách bố trí shebang, điều kiện tệp và quyền thực thi trên Linux/macOS.

Bài học chỉ dùng các nguyên tắc đang được hỗ trợ: Java 11+ source-file mode, shebang trên hệ điều hành tương ứng, cách truyền đối số và kiểm tra lỗi thực tế.