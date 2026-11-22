# Tùy chọn --enable-preview trong Java

Java phát triển nền tảng theo từng phiên bản. Một số tính năng mới được đưa vào JDK ở trạng thái **Preview** để nhà phát triển thử nghiệm, đánh giá và gửi phản hồi trước khi tính năng được hoàn thiện. Tùy chọn dòng lệnh **--enable-preview** cho phép bật các preview feature của bản phát hành Java hiện tại khi biên dịch hoặc chạy chương trình.

Đây là tùy chọn có phạm vi theo phiên bản JDK. Muốn dùng một preview feature đúng cách, phải xác định tính năng đó thuộc bản Java nào, biên dịch bằng JDK tương ứng và bật preview ở đúng giai đoạn của quy trình.

## 1. Preview feature là gì?

**Preview feature** là tính năng được công bố trong một bản phát hành Java để nhà phát triển dùng thử trước khi được quyết định hoàn thiện. Tùy tính năng, preview có thể liên quan đến ngôn ngữ Java, API thư viện hoặc máy ảo.

Một preview feature thường có các đặc điểm:

- Có tài liệu mô tả rõ tính năng và bản phát hành giới thiệu nó.
- Có thể thay đổi thiết kế, cú pháp hoặc API ở một lần preview tiếp theo.
- Có thể được hoàn thiện thành tính năng chính thức, tiếp tục preview hoặc bị loại bỏ.
- Phải được bật tường minh theo quy tắc của JDK phát hành tính năng đó.

Preview là một trạng thái phát hành có quy trình và tài liệu chính thức. Nó không có nghĩa là tính năng đã được cam kết ổn định về tương thích như các tính năng Java đã hoàn thiện.

### Vòng đời của một preview feature

Một tính năng có thể đi qua các giai đoạn:

1. **Đề xuất và phát triển:** thiết kế được thảo luận, thường được mô tả trong một JEP.
2. **Preview:** tính năng xuất hiện trong một bản phát hành Java và được bật bằng **--enable-preview**.
3. **Preview tiếp theo (nếu có):** cú pháp, API hoặc hành vi có thể được điều chỉnh dựa trên phản hồi.
4. **Final hoặc withdrawn:** tính năng có thể trở thành chính thức hoặc bị rút khỏi nền tảng.

Không phải tính năng nào cũng cần nhiều lần preview. Trạng thái và phiên bản của từng tính năng phải được tra theo tài liệu JEP và tài liệu phát hành Java tương ứng.

### Preview khác gì tính năng đã hoàn thiện?

| Khía cạnh | Preview feature | Tính năng đã hoàn thiện |
|---|---|---|
| Bật sử dụng | Cần tùy chọn preview phù hợp | Thường không cần --enable-preview |
| Tương thích giữa phiên bản | Có thể thay đổi hoặc bị rút | Theo chính sách tương thích Java thông thường |
| Mục đích | Thử nghiệm và thu thập phản hồi | Sử dụng ổn định trong nền tảng |
| Mức độ phù hợp production | Cần chấp nhận rủi ro thay đổi | Phù hợp hơn cho ứng dụng cần ổn định lâu dài |

Preview feature không nên bị nhầm với **incubator module**. Incubator module cung cấp API thử nghiệm theo cơ chế module riêng; không phải cứ API thử nghiệm nào cũng được bật bằng --enable-preview. Hãy đọc hướng dẫn của chính tính năng đang sử dụng.

## 2. --enable-preview hoạt động ở đâu?

Tùy chọn này xuất hiện ở những giai đoạn khác nhau:

- **Biên dịch:** truyền cho **javac** để compiler chấp nhận cú pháp hoặc API preview được hỗ trợ ở phiên bản đó.
- **Thực thi:** truyền cho **java** để JVM cho phép chạy chương trình sử dụng preview feature.
- **Công cụ build và kiểm thử:** cấu hình riêng cờ cho compiler và cho JVM chạy test nếu các tiến trình đó dùng preview feature.

Bật preview khi biên dịch không tự động bật preview khi chạy. Nếu mã nguồn đã biên dịch sử dụng preview feature, lệnh khởi chạy cũng cần được cấu hình tương ứng.

**--enable-preview** bật nhóm preview feature của bản phát hành hiện tại; nó không phải tùy chọn để chọn riêng một JEP cụ thể. Tính năng thực tế được dùng vẫn phụ thuộc vào mã nguồn, API và khả năng của JDK đó.

## 3. Quan hệ giữa --enable-preview, --release và --source

**javac** cần biết phiên bản ngôn ngữ và nền tảng mục tiêu. Các tùy chọn liên quan gồm:

- **--release N:** biên dịch theo phiên bản nền tảng Java N, bao gồm mức ngôn ngữ, định dạng class file và tập API Java SE tương ứng.
- **--source N:** chọn mức ngôn ngữ nguồn mà compiler chấp nhận.
- **-target N:** chọn phiên bản class file đầu ra.
- **--enable-preview:** bật preview feature của bản phát hành Java hiện tại.

Khi dùng preview, phiên bản đích phải khớp với bản phát hành của compiler đang chạy. Ví dụ, để dùng preview feature của Java 21, hãy dùng JDK 21 và chỉ định **--release 21** (hoặc **--source 21** theo nhu cầu).

~~~bash
javac --enable-preview --release 21 -d out PreviewDemo.java
~~~

Không thể dùng compiler của JDK 22 để bật preview của Java 21 bằng cách đặt **--release 21 --enable-preview**. Preview chỉ được hỗ trợ cho bản phát hành hiện tại của compiler. Nếu compiler là JDK 22, preview được bật là preview của Java 22.

**--release** thường phù hợp hơn khi cần giới hạn cả API nền tảng mục tiêu. Tránh chỉ kết hợp **-source** và **-target** rồi cho rằng chương trình chắc chắn chỉ dùng API có ở phiên bản đích.

## 4. Ví dụ: unnamed pattern preview trong Java 21

Java 21 đưa **Unnamed Patterns and Variables** vào trạng thái preview. Tính năng này cho phép dùng dấu gạch dưới _ khi không cần đặt tên cho biến được khớp bởi pattern.

Tạo tệp PreviewDemo.java:

~~~java
public class PreviewDemo {
    static String classify(Object value) {
        return switch (value) {
            case String _ -> "text";
            case Integer number -> "integer";
            case null -> "null";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("hello"));
    }
}
~~~

Trong nhánh **case String _**, chương trình chỉ cần xác định giá trị có kiểu String; không sử dụng biến đại diện cho chuỗi, nên pattern dùng _ thay cho tên biến. Nhánh **case Integer number** vẫn đặt tên number vì ví dụ có thể cần giá trị đó trong phần xử lý.

Với JDK 21, biên dịch:

~~~bash
javac --enable-preview --release 21 -d out PreviewDemo.java
~~~

Chạy:

~~~bash
java --enable-preview -cp out PreviewDemo
~~~

Output:

~~~text
text
~~~

Ví dụ này dùng preview feature của Java 21. Unnamed patterns and variables được hoàn thiện trong Java 22; vì vậy, cùng cú pháp _ có trạng thái khác nhau tùy phiên bản. Trên Java 22 trở lên, tính năng này không còn cần được bật như preview. Ví dụ minh họa vì thế phải được biên dịch và chạy bằng JDK 21 để thể hiện đúng mục đích của --enable-preview.

## 5. Vì sao phải bật preview cả khi biên dịch và chạy?

Compiler cần cờ preview để chấp nhận tính năng chưa hoàn thiện của phiên bản đó. Khi sử dụng preview language feature, class file được đánh dấu là phụ thuộc vào preview của bản phát hành cụ thể.

Khi chạy, JVM kiểm tra khả năng tương thích này. Vì vậy:

- Bỏ **--enable-preview** ở bước compile có thể khiến compiler báo lỗi cú pháp hoặc từ chối API preview.
- Bật preview lúc compile nhưng bỏ cờ ở bước run có thể khiến JVM từ chối class file preview.
- Biên dịch bằng JDK 21 rồi chạy trên JDK 22 không biến class file preview Java 21 thành class file preview Java 22.
- Class file sử dụng preview chỉ có thể chạy bằng đúng bản phát hành Java đã tạo ra nó, với preview được bật.

Một số lỗi thường gặp có thể liên quan đến việc thiếu cờ preview hoặc chạy class file trên sai phiên bản JDK. Khi gặp lỗi, cần kiểm tra cả compiler và runtime thực tế, không chỉ phiên bản Java mà IDE hiển thị.

## 6. Cấu hình khi chạy bằng công cụ build và IDE

Trong dự án dùng Maven, Gradle hoặc IDE, việc thêm cờ cho compiler là chưa đủ. Cần bảo đảm JVM khởi chạy test và ứng dụng cũng nhận được **--enable-preview**.

Thông thường cần kiểm tra các điểm sau:

1. **JDK toolchain:** compiler của dự án dùng đúng bản JDK giới thiệu preview feature.
2. **Compile task:** truyền **--enable-preview** và phiên bản **--release** tương ứng cho compiler.
3. **Test task:** truyền **--enable-preview** cho JVM chạy unit test hoặc integration test nếu test/application dùng preview feature.
4. **Run/debug configuration:** cấu hình JVM argument cho tiến trình chạy hoặc debug ứng dụng.
5. **CI pipeline:** dùng đúng JDK và truyền cờ ở cả compile lẫn test/run để kết quả trên CI khớp với máy phát triển.

Tên trường cấu hình cụ thể phụ thuộc phiên bản Maven Compiler Plugin, Surefire, Gradle và IDE. Hãy cấu hình cờ ở đúng task thay vì chỉ thêm một chuỗi compiler argument chung rồi giả định mọi JVM con đều nhận được.

Với một lệnh chạy trực tiếp, vị trí cờ có thể thấy rõ:

~~~bash
java --enable-preview -cp out PreviewDemo
~~~

Cờ này thuộc JVM được khởi chạy bởi lệnh trên. Nếu build tool fork một JVM khác để chạy test, JVM con đó cũng cần được cấu hình.

## 7. Kiểm tra môi trường và chẩn đoán lỗi

Khi sử dụng preview feature, xác định chính xác compiler và runtime đang được gọi:

~~~bash
java --version
javac --version
~~~

Hai lệnh nên trỏ đến cùng dòng JDK mà dự án dự định dùng. Nếu máy có nhiều JDK, kiểm tra **JAVA_HOME**, **PATH** và cấu hình JDK riêng trong IDE/build tool.

Một số tình huống thường gặp:

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Compiler báo preview feature chưa được bật | Thiếu --enable-preview ở lệnh javac | Thêm cờ preview và chọn đúng release |
| Compiler báo preview chỉ hỗ trợ cho release hiện tại | --release không trùng phiên bản JDK compiler | Dùng đúng JDK hoặc bỏ ý định biên dịch preview của release cũ |
| JVM từ chối class file preview | Thiếu cờ ở runtime hoặc dùng sai phiên bản Java | Bật preview và chạy trên đúng JDK phát hành class file |
| Chạy được từ terminal nhưng test thất bại | Test runner khởi chạy JVM riêng chưa nhận cờ | Cấu hình JVM arguments cho test task |
| IDE báo lỗi nhưng CLI biên dịch được | IDE dùng JDK hoặc language level khác | Đồng bộ Project SDK, compiler level và run configuration |
| Build trên CI thất bại | CI dùng JDK khác máy lập trình viên | Khóa toolchain và kiểm tra version trong pipeline |

Có thể dùng **javap -v** để xem metadata của class file. Với class file preview, thông tin phiên bản có thể cho thấy dấu hiệu preview; đây là cách kiểm tra bổ sung khi điều tra sự không tương thích giữa compiler và runtime.

## 8. Rủi ro và cách dùng có trách nhiệm

Preview feature hữu ích để đánh giá tính năng mới, thử nghiệm cú pháp và phản hồi cho quá trình phát triển Java. Tuy nhiên, vì thiết kế có thể thay đổi, việc phụ thuộc lâu dài vào preview tạo ra chi phí nâng cấp:

- Mã nguồn có thể cần sửa khi cú pháp hoặc API thay đổi.
- Mỗi lần nâng JDK có thể cần cập nhật compiler flags và runtime flags.
- Class file preview bị ràng buộc với đúng bản phát hành Java tạo ra nó.
- Môi trường production, CI, test và developer machine đều phải thống nhất phiên bản.
- Một tính năng có thể bị rút trước khi trở thành chính thức.

Trước khi dùng preview trong dự án, hãy xác định mục tiêu thử nghiệm, phiên bản JDK, phạm vi mã bị ảnh hưởng và kế hoạch chuyển đổi khi tính năng được hoàn thiện hoặc bị thay đổi. Với hệ thống cần tương thích lâu dài, nên ưu tiên API và ngôn ngữ đã được hoàn thiện.

## 9. Checklist sử dụng --enable-preview

- Xác định tên preview feature và JDK release giới thiệu nó.
- Đọc JEP hoặc tài liệu phát hành để xác nhận trạng thái của tính năng trong release đang dùng.
- Cài đúng JDK release đó; kiểm tra **java --version** và **javac --version**.
- Truyền **--enable-preview** cho compiler và dùng **--release** hoặc **--source** khớp với release hiện tại.
- Truyền **--enable-preview** cho JVM chạy ứng dụng.
- Cấu hình riêng JVM chạy test, integration test và debug.
- Dùng cùng JDK release trên máy phát triển và CI.
- Không chạy class file preview bằng một release khác.
- Đánh giá rủi ro thay đổi trước khi đưa preview feature vào production.
- Khi tính năng trở thành chính thức, loại bỏ cờ preview nếu không còn tính năng preview nào khác cần dùng và cập nhật cấu hình về chế độ ổn định.

## 10. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Preview feature | Tính năng được phát hành để thử nghiệm và thu thập phản hồi |
| --enable-preview | Bật preview feature của JDK release hiện tại |
| --release | Chọn phiên bản nền tảng Java mục tiêu khi biên dịch |
| --source | Chọn mức ngôn ngữ nguồn |
| -target | Chọn phiên bản class file đầu ra |
| JEP | Java Enhancement Proposal, tài liệu mô tả đề xuất và trạng thái phát triển tính năng |
| Incubator module | Module cung cấp API thử nghiệm theo cơ chế incubator |
| Class file preview | Class file phụ thuộc vào preview feature của một bản phát hành cụ thể |
| Runtime argument | Tùy chọn được truyền cho JVM khi khởi chạy ứng dụng |

Điểm cốt lõi cần nhớ: **--enable-preview** luôn gắn với bản phát hành JDK hiện tại. Hãy bật cờ ở cả bước biên dịch và bước chạy, giữ cùng phiên bản JDK xuyên suốt toolchain, và chỉ dùng preview khi dự án chấp nhận khả năng phải thay đổi mã nguồn trong tương lai.