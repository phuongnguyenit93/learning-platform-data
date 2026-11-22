# Chọn JDK còn được hỗ trợ để học cú pháp Java chính thức (bối cảnh Java 14)

> **Phạm vi:** Java 14 là mốc lịch sử của ngôn ngữ, không phải phiên bản JDK nên cài đặt cho việc học mới. Bài này hướng dẫn chọn JDK đang nhận bản cập nhật, nhận diện cú pháp đã trở thành tính năng chính thức và kiểm tra mã bằng trình biên dịch hiện đại. Thông tin hỗ trợ phiên bản được đối chiếu tại **tháng 11/2026**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **phiên bản ngôn ngữ Java**, **JDK dùng để phát triển** và **phiên bản Java mà chương trình nhắm tới**.
2. Chọn JDK có chính sách cập nhật phù hợp, thay vì cài JDK 14 đã hết vòng đời hỗ trợ thông thường.
3. Nhận biết cú pháp nào **đã chính thức** tại Java 14, cú pháp nào chỉ ở giai đoạn **preview** khi đó nhưng đã chính thức ở phiên bản sau.
4. Dùng `java`, `javac` và `javac --release` để kiểm chứng ví dụ mà không cần bật tính năng thử nghiệm.

## 2. Ba khái niệm cần tách bạch

- **Java SE / phiên bản ngôn ngữ:** tập cú pháp và API được đặc tả cho một mốc phát hành, chẳng hạn Java 14, 17, 21 hay 25. Cú pháp đã được chuẩn hóa ở Java 14 thường vẫn là một phần của Java hiện đại.
- **JDK (Java Development Kit):** bộ công cụ gồm `javac` để biên dịch, `java` để chạy và các công cụ phát triển khác. Một JDK mới có thể biên dịch mã dùng cú pháp cũ khi phiên bản đích còn được trình biên dịch hỗ trợ.
- **Phiên bản đích (target/release):** quy định mã nguồn, API và định dạng bytecode được phép sử dụng khi biên dịch. Phiên bản JDK đang cài có thể **mới hơn** phiên bản đích của bài thực hành.

Ví dụ: cài **JDK 25** rồi biên dịch ví dụ `switch` với `--release 14`. Bạn đang dùng trình biên dịch được cập nhật để kiểm tra quy tắc của Java 14; bạn **không cần** cài hoặc chạy JDK 14.

**LTS (Long-Term Support)** là chính sách duy trì bản cập nhật của nhà cung cấp bản phân phối JDK, không phải một loại cú pháp Java. Hai bản phân phối cùng mang số phiên bản 21 có thể có thời hạn cập nhật, giấy phép và kênh hỗ trợ khác nhau.

## 3. Nên chọn JDK nào ở thời điểm hiện tại?

| Trường hợp | Lựa chọn | Lý do |
| --- | --- | --- |
| Bắt đầu học mới, muốn một JDK dùng lâu dài | **JDK 25 LTS**, lấy bản vá mới nhất từ nhà cung cấp uy tín | Là nhánh LTS mới nhất tại tháng 11/2026; hỗ trợ cú pháp chính thức của các phiên bản cũ và hiện đại. |
| Giáo trình, IDE hoặc dự án đang chuẩn hóa ở Java 21 | **JDK 21 LTS** còn được nhà cung cấp cập nhật | Đủ để học `switch` Java 14 và các cú pháp chính thức đến Java 21; tránh thay đổi phiên bản dự án tùy tiện. |
| Dự án đang bắt buộc tương thích Java 17 | **JDK 17 LTS** có cập nhật hợp lệ | Phù hợp yêu cầu dự án; không cần nâng phiên bản chỉ để học `switch` Java 14. |
| Muốn khám phá phát hành tính năng mới nhất | JDK 27 hiện là nhánh phát hành ngắn hạn | Có thể dùng riêng để thử tính năng mới, nhưng không phải lựa chọn mặc định cho môi trường học dài hạn. |
| Định cài JDK 14 vì tên module là “Java 14” | **Không chọn làm JDK chính** | Java 14 là phát hành non-LTS năm 2020, đã bị các bản phát hành tiếp theo thay thế trong lịch hỗ trợ thông thường. |

**Quy tắc chọn nhanh:** nếu không bị ràng buộc bởi giáo trình/dự án, chọn **JDK 25 LTS**; nếu môi trường yêu cầu Java 21 thì chọn **JDK 21 LTS**. Luôn kiểm tra **chính sách cập nhật của đúng bản phân phối** trước khi cài. Với Oracle JDK, điều khoản cấp phép các bản cập nhật cũng phụ thuộc dòng phiên bản; chẳng hạn các bản cập nhật Oracle JDK 21 từ tháng 10/2026 chuyển sang điều khoản OTN. Đây là lý do cần đọc điều khoản của nhà cung cấp, không suy luận quyền sử dụng chỉ từ nhãn “LTS”.

Có thể tham khảo **Eclipse Temurin** (Adoptium) hoặc JDK do nhà cung cấp dự án/đơn vị đào tạo chỉ định. Chọn đúng hệ điều hành và kiến trúc máy (`x64` hoặc `ARM64`), đúng dòng LTS và **bản cập nhật bảo mật mới nhất** của dòng đó. Tải từ trang chính thức; tránh các bộ cài JDK 14 không còn được bảo trì chỉ để chạy ví dụ cũ.

## 4. Java 14 đã chính thức hóa cú pháp nào?

Một tính năng **preview** có thể thay đổi cú pháp hoặc bị rút lại ở các bản kế tiếp. Vì vậy, hãy dạy và sử dụng **hình thức đã chính thức** ở bản Java hiện đại, đồng thời ghi đúng mốc mà nó trở thành chính thức.

| Cú pháp / tính năng | Trạng thái ở Java 14 | Chính thức từ | Cách hiểu khi học hôm nay |
| --- | --- | --- | --- |
| `switch` expression, nhánh `case ... ->`, `yield` | **Chính thức** | **Java 14** (JEP 361) | Trọng tâm cú pháp mới chính thức ở Java 14; dùng được với JDK 17/21/25. |
| Text block `"""..."""` | Preview lần hai | **Java 15** (JEP 378) | Học theo ngữ nghĩa chính thức từ Java 15, không sao chép hướng dẫn preview của Java 14. |
| `record` | Preview | **Java 16** (JEP 395) | Cú pháp `record` ngày nay là chính thức, nhưng không được khẳng định là chính thức từ Java 14. |
| Pattern matching cho `instanceof` | Preview | **Java 16** (JEP 394) | Dùng cú pháp chính thức khi phiên bản đích từ Java 16 trở lên. |
| `sealed` class/interface | Chưa chính thức ở Java 14 | **Java 17** (JEP 409) | Cú pháp hiện hành; không gán nhầm vào các tính năng đã chính thức ở Java 14. |
| Record patterns và pattern matching cho `switch` | Chưa chính thức ở Java 14 | **Java 21** (JEP 440, 441) | Phân biệt với `switch` expression Java 14: cùng từ khóa nhưng là khả năng ngôn ngữ khác. |

**Kết luận kỹ thuật:** trong các thay đổi cú pháp nổi bật của Java 14, **`switch` expressions là tính năng đã chính thức hóa ở chính mốc 14**. Các nội dung khác trong bảng vẫn hữu ích ngày nay ở **dạng chính thức sau này**, nhưng không nên dạy cú pháp preview cũ hoặc yêu cầu bật `--enable-preview` cho một bài chỉ học cú pháp chính thức.

Các cấu trúc quen thuộc có trước Java 14 như `var` cho biến cục bộ (chính thức từ Java 10), lambda và `try-with-resources` vẫn hữu ích, nhưng không phải điểm mới được Java 14 chính thức hóa.

## 5. Kiểm tra JDK đã cài

Mở terminal hoặc cửa sổ lệnh tại máy phát triển, chạy:

~~~bash
java --version
javac --version
javac --help
~~~

Đọc kết quả theo nguyên tắc:

- `java --version` cho biết runtime mà lệnh `java` hiện tại sử dụng; `javac --version` cho biết trình biên dịch đã được tìm thấy trên `PATH`. Hai lệnh nên thuộc cùng dòng JDK mà bạn chủ ý dùng.
- Nếu có `java` nhưng không có `javac`, hoặc phiên bản của hai lệnh lệch nhau ngoài ý muốn, kiểm tra `JAVA_HOME`, `PATH` và cấu hình JDK của IDE.
- `javac --help` hiển thị các giá trị `--release` mà trình biên dịch đang cài hỗ trợ. Không mặc định mọi JDK tương lai đều hỗ trợ biên dịch cho vô hạn phiên bản cũ.
- Với IntelliJ IDEA, VS Code hoặc công cụ build, kiểm tra cả **Project SDK / Java Toolchain** và **language level / release target**; cài JDK trong hệ điều hành không tự động đổi phiên bản biên dịch của mọi dự án.

Dấu hiệu đã sẵn sàng: bạn xác định rõ **JDK đang dùng**, **phiên bản đích**, và **cách chạy chương trình**. Số phiên bản hiển thị có thể có nhiều thành phần bản vá như `25.0.x`; không cần trùng chính xác giữa các máy nếu cùng dòng được hỗ trợ và đáp ứng yêu cầu bài học.

## 6. Ví dụ chạy được: `switch` expression chính thức từ Java 14

Tạo tệp **`Switch14Demo.java`** với nội dung:

~~~java
public class Switch14Demo {
    static String status(int hours) {
        return switch (hours) {
            case 0 -> "free";
            case 1, 2, 3, 4 -> "part-time";
            default -> {
                String label = hours >= 8 ? "full-time" : "other";
                yield label;
            }
        };
    }

    public static void main(String[] args) {
        System.out.println(status(0));
        System.out.println(status(3));
        System.out.println(status(8));
    }
}
~~~

Dùng JDK đang được hỗ trợ (ví dụ 21 hoặc 25) và biên dịch theo quy tắc Java 14:

~~~bash
javac --release 14 Switch14Demo.java
java Switch14Demo
~~~

Kết quả chuẩn:

~~~text
free
part-time
full-time
~~~

**Giải thích:**

1. `return switch (hours) { ... };` sử dụng toàn bộ `switch` như **một biểu thức trả về giá trị**; khác với `switch` statement cổ điển chỉ điều khiển luồng.
2. `case 1, 2, 3, 4 ->` gộp nhiều nhãn; nhánh mũi tên không rơi qua nhánh kế tiếp (không có fall-through mặc định).
3. Nhánh `default -> { ... yield label; }` tính giá trị trong một khối lệnh; `yield` trả giá trị **cho biểu thức `switch`**, không phải trả khỏi phương thức. Đừng thay `yield` bằng `return` trong trường hợp này.
4. Mọi đầu vào của `switch` expression cần được bao phủ bởi nhánh phù hợp. `default` ở đây xử lý các giá trị còn lại.
5. Tùy chọn `--release 14` kiểm tra cú pháp, API được phép dùng và class file phù hợp Java 14. Máy vẫn dùng **JDK hiện tại** để biên dịch và chạy; tùy chọn này **không đổi JDK đang chạy thành JDK 14**.

Đối với bài thực hành Java 14, mẫu trên dùng cú pháp **đã chính thức**, không cần `--enable-preview`. Nếu `javac` báo không hỗ trợ `--release 14`, xem lại `javac --help` và dùng một JDK được hỗ trợ có cung cấp mức đích cần thiết; không tự động chuyển sang cài JDK 14 hết vòng đời.

## 7. Ví dụ phân biệt: cú pháp chính thức hôm nay nhưng chưa chính thức ở Java 14

Tạo tệp **`ModernSyntaxDemo.java`**:

~~~java
record Course(String name, int level) {}

public class ModernSyntaxDemo {
    public static void main(String[] args) {
        Object item = new Course("Java", 14);

        if (item instanceof Course course) {
            System.out.println(course.name() + " / " + course.level());
        }
    }
}
~~~

Với JDK 21 hoặc 25, biên dịch và chạy:

~~~bash
javac --release 21 ModernSyntaxDemo.java
java ModernSyntaxDemo
~~~

Kết quả chuẩn:

~~~text
Java / 14
~~~

Tại sao có thể học đoạn mã này, nhưng không nên giới thiệu nó là “cú pháp chính thức của Java 14”?

- `record Course(...)` mô tả một lớp mang dữ liệu, có constructor, các accessor `name()` và `level()`; `record` trở thành tính năng chính thức ở **Java 16**.
- `item instanceof Course course` vừa kiểm tra kiểu vừa tạo biến pattern `course`; tính năng này cũng chính thức ở **Java 16**.
- `--release 21` chấp nhận cả hai vì Java 21 đã bao gồm dạng chính thức. Nếu đổi sang `--release 14`, mã bị từ chối vì các cú pháp đó **chưa là cú pháp chính thức có sẵn của Java 14**. Đây là kết quả mong đợi, không phải lỗi cài JDK.

**Lưu ý về ý nghĩa:** thành phần của `record` là `final` ở mức tham chiếu, nhưng nếu một thành phần chứa đối tượng có thể thay đổi thì `record` không tự động biến toàn bộ đồ thị đối tượng thành bất biến sâu. Đây là cách hiểu vẫn đúng ở Java hiện đại.

## 8. `--release` dùng để làm gì, và không làm gì?

Với `javac`, `--release N` là lựa chọn phù hợp khi muốn giới hạn mã theo **nền tảng Java N** mà trình biên dịch còn hỗ trợ. Nó phối hợp kiểm tra:

- Cú pháp ngôn ngữ có ở phiên bản đích.
- Các API Java SE/JDK được hỗ trợ và xuất ra ở phiên bản đích.
- Định dạng bytecode tương thích với phiên bản đích.

Điều đó hữu ích hơn chỉ đặt `-source N` và `-target N` mà bỏ qua API đích: mã có thể vẫn vô tình gọi API chỉ xuất hiện ở JDK mới hơn. Không kết hợp `--release` với `--source`/`--target` trong cùng lệnh.

Dù class file được biên dịch cho Java 14, **không nên triển khai hoặc học trên runtime Java 14 đã hết cập nhật**. Hãy chạy ví dụ trên JDK LTS hiện hành. Nếu một ứng dụng thật bắt buộc chạy trên phiên bản cũ, đó là ràng buộc triển khai cần được đánh giá riêng về bảo mật và kế hoạch nâng cấp.

## 9. Cách quyết định phiên bản theo từng tình huống

**Tình huống A — học riêng nội dung Java 14:** cài JDK 25 LTS có cập nhật; làm bài `switch` expression ở mục 6; biên dịch với `--release 14` để bảo đảm không vô tình dùng cú pháp/API xuất hiện sau Java 14.

**Tình huống B — khóa học nhắm Java 21:** dùng JDK 21 LTS theo cấu hình lớp hoặc JDK 25 theo chính sách khóa học; đặt target Java 21. Bạn có thể học `switch` Java 14 cùng `record`/pattern matching đã chính thức sau đó.

**Tình huống C — dự án cố định ở Java 17:** dùng JDK 17 được nhà cung cấp tiếp tục cập nhật; đặt toolchain/`--release 17`. Không đưa pattern matching cho `switch` (chính thức từ Java 21) vào nguồn Java 17.

**Tình huống D — đọc bài viết Java 14 cũ có lệnh `--enable-preview`:** xác định JEP và mốc chính thức trước. Thay hướng dẫn cũ bằng dạng chính thức phù hợp phiên bản đích; không sao chép cú pháp thử nghiệm chỉ vì ví dụ từng chạy được năm 2020.

Đối với mọi tình huống, thứ tự ra quyết định là: **yêu cầu tương thích → trạng thái chính thức của cú pháp → JDK/vendor còn cập nhật → cấu hình compiler và IDE → biên dịch, chạy thực tế**.

## 10. Lỗi thường gặp và cách tự kiểm tra

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `javac` không tồn tại dù `java` chạy được | `PATH` trỏ nhầm runtime hoặc JDK chưa được cấu hình | Cài/chọn đầy đủ JDK, kiểm tra `JAVA_HOME` và `PATH`. |
| `switch` expression báo lỗi cú pháp | Compiler target thấp hơn Java 14 hoặc IDE dùng compiler khác | Chọn JDK hiện hành và `--release` từ 14 trở lên; kiểm tra language level. |
| `record` không được chấp nhận với `--release 14` | `record` chưa chính thức ở Java 14 | Dùng target từ 16 trở lên nếu bài yêu cầu `record` chính thức. |
| Bài cũ yêu cầu `--enable-preview` | Hướng dẫn được viết ở giai đoạn thử nghiệm | Tra mốc chính thức và dùng cú pháp đã chốt, không bật preview cho bài này. |
| Mã chạy trên máy mình nhưng không biên dịch trên môi trường dự án | IDE/compiler và toolchain đang đặt khác phiên bản đích | Đồng bộ cấu hình JDK, target, build tool; kiểm tra lại bằng lệnh `javac --release` phù hợp. |
| Thấy “LTS” nên mặc định được cập nhật và miễn phí trong mọi hoàn cảnh | LTS, bảo trì và giấy phép là các cam kết khác nhau | Đọc trang hỗ trợ, ngày kết thúc cập nhật và giấy phép của đúng nhà cung cấp. |

## 11. Tự luyện và tiêu chí hoàn thành

1. Tự viết một `switch` expression nhận số ngày trong tuần và trả về chuỗi `"weekday"` hoặc `"weekend"`. Dùng nhánh mũi tên và một `default` hợp lệ. Biên dịch với `--release 14`. Xác minh đầu vào `6` cho `"weekend"` và `2` cho `"weekday"`.
2. Tạo một `record` có hai thành phần và đọc dữ liệu qua accessor. Biên dịch với `--release 21`; giải thích vì sao ví dụ này không thuộc nhóm cú pháp **đã chính thức ở Java 14**.
3. Kiểm tra JDK thực tế bằng `java --version`, `javac --version` và `javac --help`. Ghi lại **phiên bản JDK**, **phiên bản đích** và **nguồn hỗ trợ của bản phân phối** mà bạn sử dụng.

Bạn đạt mục tiêu khi trả lời được ba câu: **(a)** Java 14 chính thức hóa cú pháp nổi bật nào? **(b)** vì sao vẫn học được cú pháp ấy trên JDK 21/25? **(c)** làm sao biết một tính năng từng preview đã trở thành chính thức trước khi đưa vào mã dự án?

## 12. Tài liệu chuẩn để đối chiếu khi phiên bản thay đổi

- [Oracle — Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html): danh sách LTS, quy tắc hỗ trợ và mốc thời gian.
- [Eclipse Adoptium — Temurin Support](https://adoptium.net/support/): lịch phát hành, bản vá và cam kết cập nhật theo nhánh.
- [Oracle — Java SE Language Changes by Release](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html): mốc chính thức/preview của `switch`, text blocks, `record`, `instanceof` pattern và những cú pháp về sau.
- [Oracle — `javac` (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): ý nghĩa và giới hạn của `--release`.
- [Oracle — Java Downloads](https://www.oracle.com/java/technologies/downloads/): xác nhận nhánh JDK hiện hành và nhánh LTS mới nhất.
- [Oracle — JDK 21 licensing update (2026)](https://blogs.oracle.com/java/jdk-21-approaches-end-of-permissive-license): bối cảnh giấy phép cần xét khi chọn riêng **Oracle JDK 21**.

**Nguyên tắc giữ cho bài học có giá trị lâu dài:** cập nhật JDK theo bản vá và chính sách nhà cung cấp; biên dịch theo **phiên bản đích thực sự cần**; học **cú pháp chính thức** từ tài liệu đặc tả hiện hành, thay vì giữ lại cú pháp preview hoặc chỉ dẫn cài đặt đã hết hạn.