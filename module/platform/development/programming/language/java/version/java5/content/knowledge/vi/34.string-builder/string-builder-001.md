# Chuỗi có thể thay đổi và vai trò của StringBuilder

## 1. Hai nhu cầu khác nhau: giữ giá trị và xây dựng nội dung

Trong chương trình, có lúc ta cần một giá trị văn bản ổn định như tên người dùng, mã đơn hàng hoặc thông báo đã hoàn chỉnh. Có lúc ta đang **xây dựng** văn bản từng bước: thêm tiêu đề, duyệt các phần tử, thêm dấu phân cách rồi tạo kết quả cuối.

Hai kiểu dữ liệu phục vụ hai vai trò:

- **String** biểu diễn giá trị văn bản bất biến: nội dung của một đối tượng String không đổi sau khi tạo.
- **StringBuilder** biểu diễn một dãy ký tự có thể sửa đổi: có thể thêm, chèn, xóa hoặc thay thế nội dung trong cùng một đối tượng.

“Chuỗi có thể thay đổi” trong bài này nói về dãy ký tự được StringBuilder quản lý. Nó không có nghĩa String tự trở thành có thể sửa đổi.

Hình dung String là bản nội dung đã chốt, còn StringBuilder là bản nháp đang biên soạn. Khi làm xong, gọi **toString()** để lấy một String có thể truyền ra ngoài.

```text
Các phần dữ liệu
      |
      v
StringBuilder: xây dựng và chỉnh sửa
      |
      | toString()
      v
String: giá trị kết quả ổn định
```

Đây là vai trò của StringBuilder trong Java hiện đại; không cần thay mọi String hoặc mọi biểu thức nối chuỗi bằng StringBuilder.

## 2. Bất biến của đối tượng khác việc gán lại biến

Đoạn minh họa:

```java
String text = "Java";
text = text + " 21";
```

Biến text chuyển sang tham chiếu tới kết quả mới. Đối tượng String ban đầu chứa Java không bị sửa thành Java 21.

Nếu hai biến cùng tham chiếu String ban đầu, gán lại một biến không làm nội dung mà biến kia thấy thay đổi:

```java
String first = "Java";
String second = first;
first = first + " 21";
// first:  "Java 21"
// second: "Java"
```

Với StringBuilder, phép append sửa nội dung của chính đối tượng:

```java
StringBuilder first = new StringBuilder("Java");
StringBuilder second = first;
first.append(" 21");
// first va second cung nhin thay "Java 21".
```

Hai biến không tạo hai bản nháp độc lập. Chúng là **hai tham chiếu tới cùng một đối tượng**, nên sự thay đổi qua tham chiếu này được quan sát qua tham chiếu kia.

Phân biệt này quan trọng khi truyền builder cho một hàm: hàm có thể sửa đối tượng mà nơi gọi vẫn đang dùng. Nếu chỉ muốn truyền giá trị văn bản ổn định, String thường là hợp đồng rõ ràng hơn.

Tính bất biến của String và quyền lựa chọn cách triển khai phép nối thuộc về Java được mô tả trong [Java SE 21 String API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html).

## 3. Cơ chế cốt lõi của StringBuilder

### 3.1. Nội dung được giữ trong vùng lưu trữ có thể mở rộng

StringBuilder giữ dãy ký tự hiện tại cùng một vùng lưu trữ nội bộ. Khi thêm nội dung, đối tượng sửa trạng thái đang giữ. Nếu vùng hiện tại không đủ, nó có thể cấp phát vùng lớn hơn.

Hai số đo cần phân biệt:

| Phương thức | Ý nghĩa |
| --- | --- |
| length() | Độ dài nội dung hiện tại tính theo đơn vị char UTF-16 |
| capacity() | Sức chứa hiện có trước khi cần mở rộng vùng lưu trữ |

Một builder có thể có capacity lớn nhưng length bằng 0. Đặt trước sức chứa không tạo ra các ký tự hiển thị trong nội dung. Cũng không nên kết luận mỗi lần append đều không cấp phát: vùng nội bộ đôi khi phải mở rộng và đối số có thể cần chuyển thành văn bản.

Không cần biết cấu trúc mảng nội bộ cụ thể của từng JDK để sử dụng đúng API. Chương trình nên dựa vào hợp đồng nội dung, độ dài và sức chứa thay vì giả định cách bố trí byte trong bộ nhớ.

### 3.2. append sửa đối tượng và cho phép nối lời gọi

```java
StringBuilder result = new StringBuilder();
result.append("count=").append(3).append(", ready=").append(true);
String text = result.toString();
// text: "count=3, ready=true"
```

append có các phiên bản nhận nhiều kiểu dữ liệu. Với số và boolean trong ví dụ, nó thêm biểu diễn văn bản tương ứng.

Các lời gọi append trên trả lại **chính builder đang được sửa**, nên có thể nối nhiều lời gọi trong cùng biểu thức. Không cần gán lại sau mỗi append để nội dung có hiệu lực.

Một biến khai báo final vẫn có thể tham chiếu đối tượng có thể sửa:

```java
final StringBuilder result = new StringBuilder();
result.append("A");
// result = new StringBuilder(); // Khong hop le: gan lai bien final.
```

final hạn chế việc gán lại biến, không biến đối tượng StringBuilder thành bất biến.

### 3.3. toString tạo giá trị kết quả độc lập với sửa đổi sau đó

```java
StringBuilder draft = new StringBuilder("Ready");
String published = draft.toString();
draft.append("!");

// published van la "Ready".
// draft hien chua "Ready!".
```

String đã nhận không phải một cửa sổ theo dõi builder. Nó giữ nội dung tại thời điểm tạo và không đổi khi builder bị append, xóa hoặc chỉnh sửa về sau.

Đây là ranh giới hữu ích: dùng đối tượng có thể sửa trong quá trình xây dựng, sau đó trả giá trị bất biến ra ngoài. Không cần đưa builder ra khỏi hàm chỉ để trả một kết quả văn bản.

Các hợp đồng append, toString và khả năng sửa đổi được quy định trong [Java SE 21 StringBuilder API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/StringBuilder.html).

## 4. Chương trình hoàn chỉnh để kiểm chứng

Lưu **MutableTextDemo.java**. Chương trình dùng cú pháp và API có trên Java 17 trở lên, không cần thư viện ngoài.

```java
public class MutableTextDemo {
    private static String buildSummary(String title, String[] steps) {
        StringBuilder result = new StringBuilder();
        result.append(title).append(": ");
        for (int i = 0; i < steps.length; i++) {
            if (i > 0) {
                result.append(", ");
            }
            result.append(steps[i]);
        }
        return result.toString();
    }

    public static void main(String[] args) {
        String original = "Java";
        String combined = original.concat(" 21");
        System.out.println("original=[" + original + "]");
        System.out.println("combined=[" + combined + "]");

        StringBuilder builder = new StringBuilder("Java");
        StringBuilder alias = builder;
        StringBuilder returned = builder.append(" 21");
        String snapshot = builder.toString();
        alias.append("!");

        System.out.println("same-alias=" + (alias == builder));
        System.out.println("same-returned=" + (returned == builder));
        System.out.println("builder=[" + builder + "]");
        System.out.println("snapshot=[" + snapshot + "]");

        StringBuilder left = new StringBuilder("same");
        StringBuilder right = new StringBuilder("same");
        System.out.println("builder-equals=" + left.equals(right));
        System.out.println("text-equals=" + left.toString().equals(right.toString()));

        String summary = buildSummary(
                "Steps", new String[]{"parse", "validate", "publish"});
        System.out.println("summary=[" + summary + "]");

        StringBuilder unicode = new StringBuilder("A\uD83D\uDE00B");
        System.out.println("utf16-length=" + unicode.length());
        System.out.println("code-points=" + unicode.codePointCount(0, unicode.length()));

        builder.setLength(0);
        System.out.println("cleared-length=" + builder.length());
        System.out.println("snapshot-after-clear=[" + snapshot + "]");
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 MutableTextDemo.java
java MutableTextDemo
```

Kết quả chuẩn:

```text
original=[Java]
combined=[Java 21]
same-alias=true
same-returned=true
builder=[Java 21!]
snapshot=[Java 21]
builder-equals=false
text-equals=true
summary=[Steps: parse, validate, publish]
utf16-length=4
code-points=3
cleared-length=0
snapshot-after-clear=[Java 21]
```

Ý nghĩa các nhóm kết quả:

- original không đổi sau concat; combined giữ giá trị nối mới.
- alias và returned cùng tham chiếu builder, nên cả hai phép kiểm tra tham chiếu đều true.
- alias.append("!") sửa đối tượng chung; snapshot được tạo trước đó vẫn giữ Java 21.
- Hai builder riêng có cùng nội dung không tự được equals xem là bằng nhau.
- buildSummary tạo một builder cục bộ, thêm dấu phẩy đúng vị trí và trả String hoàn chỉnh.
- setLength(0) làm nội dung builder rỗng nhưng không thay String snapshot đã có.

Không dùng kết quả đo tốc độ trong ví dụ này: mục tiêu là kiểm chứng hành vi của đối tượng và thiết kế kết quả, không phải kết luận hiệu năng.

## 5. Khi nào StringBuilder có vai trò rõ ràng?

### 5.1. Tích lũy nhiều phần trong vòng lặp

Ví dụ tạo báo cáo từ số lượng phần tử chỉ biết khi chạy:

```java
StringBuilder report = new StringBuilder();
for (String item : items) {
    report.append("- ").append(item).append('\n');
}
String text = report.toString();
```

Đây là đoạn minh họa trong một phương thức có biến items. Builder thể hiện trực tiếp ý định “tích lũy nội dung vào cùng một bản nháp”.

Nếu thay bằng text = text + part ở mỗi lượt lặp, mỗi kết quả String vẫn phải có giá trị bất biến. Với cách thực thi thông thường, việc liên tục dựng lại tiền tố đã dài có thể gây sao chép lặp và cấp phát trung gian đáng kể. Builder giúp tránh mô hình dựng lại toàn bộ giá trị sau từng phần, dù đôi khi vẫn cần mở rộng vùng nội bộ.

Không kết luận một con số tốc độ cố định hoặc nói “StringBuilder luôn nhanh hơn”. Kết quả phụ thuộc dữ liệu, JDK và tối ưu của JVM. Khi hiệu năng là yêu cầu thực tế, đo bằng công cụ và tình huống phù hợp thay vì đồng hồ của một vòng lặp nhỏ.

### 5.2. Nhiều nhánh điều kiện cùng đóng góp vào một kết quả

Builder hữu ích khi phần nội dung chỉ được thêm trong một số nhánh:

```java
StringBuilder message = new StringBuilder("Order accepted");
if (priority) {
    message.append(" [priority]");
}
if (trackingCode != null) {
    message.append(" tracking=").append(trackingCode);
}
return message.toString();
```

Đây là thân phương thức minh họa có biến priority và trackingCode. Trạng thái đang xây dựng nằm trong một biến, còn kết quả cuối được chốt ở một điểm.

### 5.3. Chỉnh sửa một bản nháp theo vị trí

StringBuilder còn có insert, delete, replace, setCharAt và reverse. Chúng thể hiện các thao tác chỉnh sửa, khác với chỉ tạo một String mới sau mỗi bước.

Bài này giới thiệu vai trò nên chưa đi sâu toàn bộ quy tắc chỉ số. Khi sửa theo vị trí, phải kiểm tra phạm vi hợp lệ và hiểu đơn vị UTF-16; không coi mỗi vị trí char đều tương ứng trọn một ký tự hiển thị.

## 6. Khi nào nên chọn công cụ đơn giản hơn?

| Nhu cầu | Lựa chọn thường rõ ràng |
| --- | --- |
| Một giá trị văn bản được lưu và truyền đi | String |
| Một biểu thức nối ngắn, số phần cố định | Toán tử + |
| Ghép danh sách chuỗi với một dấu phân cách | String.join hoặc StringJoiner |
| Văn bản theo mẫu có quy tắc định dạng | formatted hoặc công cụ định dạng phù hợp |
| Tích lũy nhiều phần qua vòng lặp, điều kiện, chỉnh sửa | StringBuilder |

Biểu thức ngắn như "Hello, " + name + "!" thường dễ đọc. Trình biên dịch và JVM có thể tối ưu phép nối; không được khẳng định mọi biểu thức dùng dấu cộng đều tạo một StringBuilder theo một cách cố định hoặc mỗi dấu cộng nhất thiết tương ứng một số cấp phát cố định.

Với một mảng chuỗi đã có sẵn và chỉ cần dấu phân cách, String.join(", ", values) có thể rõ hơn việc tự quản lý builder và vị trí dấu phẩy. Builder phát huy vai trò khi cần điều khiển quá trình tạo nội dung chi tiết hơn.

## 7. Quyền sở hữu và chia sẻ đối tượng

### 7.1. Builder cục bộ giúp giới hạn nơi có thể sửa

Hàm buildSummary trong chương trình có vòng đời đơn giản:

1. Tạo builder trong hàm.
2. Thêm các phần theo thứ tự.
3. Chuyển thành String.
4. Trả String cho nơi gọi.

Không nơi nào bên ngoài có thể tiếp tục sửa builder đó. Cách này giúp kết quả rõ ràng và tránh việc hai phần của chương trình vô tình sửa chung một bản nháp.

Nếu một API nhận StringBuilder để bổ sung nội dung, phải nói rõ nó **sửa đối tượng được truyền vào**. Nếu API chỉ cần nhận văn bản để đọc, String hoặc CharSequence có thể diễn tả nhu cầu tốt hơn, nhưng CharSequence tự nó không đảm bảo đối tượng bất biến.

### 7.2. Không tự an toàn khi nhiều luồng cùng sửa

StringBuilder không cung cấp bảo đảm đồng bộ cho việc nhiều luồng đồng thời truy cập và thay đổi. Hướng đơn giản thường là để mỗi lần xử lý có một builder cục bộ, thay vì chia sẻ một builder dùng chung.

Nếu thật sự cần chia sẻ, phải có cơ chế đồng bộ cho toàn bộ thao tác liên quan. Việc thay lớp bằng một kiểu có phương thức đồng bộ không tự làm mọi chuỗi thao tác “kiểm tra rồi sửa” trở thành nguyên tử. Hãy thiết kế quyền sở hữu trước khi chọn cách khóa.

## 8. Những điểm dễ hiểu nhầm

### 8.1. equals của StringBuilder không so nội dung như String

Hai builder độc lập cùng chứa same vẫn cho equals bằng false trong ví dụ. StringBuilder không ghi đè equals để so dãy ký tự; nó kế thừa cách so theo danh tính đối tượng.

Khi cần một giá trị văn bản để so sánh hoặc làm khóa có ý nghĩa nội dung, chuyển sang String và dùng phép so sánh phù hợp. Đừng dùng việc hai builder có cùng toString làm bằng chứng rằng chúng là cùng một đối tượng.

### 8.2. length không luôn bằng số ký tự người dùng nhìn thấy

Chuỗi trong ví dụ có A, một ký tự bổ sung được viết bằng cặp surrogate \uD83D\uDE00, rồi B. length là 4 đơn vị UTF-16, còn codePointCount là 3 điểm mã.

Ngay cả số điểm mã cũng chưa luôn bằng số ký tự hiển thị mà người dùng cảm nhận, vì dấu kết hợp và các chuỗi ký tự có thể tạo một cụm hiển thị. Sửa hoặc xóa một char tùy ý có thể tách đôi cặp surrogate.

Vì vậy StringBuilder là công cụ sửa dãy ký tự, không tự giải quyết mọi quy tắc biên tập văn bản Unicode.

### 8.3. Xóa nội dung không đồng nghĩa giảm sức chứa

setLength(0) làm độ dài bằng 0 để có thể tái dùng builder, nhưng không hứa trả toàn bộ sức chứa về mức ban đầu. Builder từng chứa dữ liệu lớn có thể tiếp tục giữ vùng lưu trữ lớn.

Không cần tái sử dụng một builder khổng lồ cho mọi tác vụ chỉ để tránh tạo đối tượng mới. Với dữ liệu nhỏ và vòng đời ngắn, một builder cục bộ mới thường dễ kiểm soát hơn.

### 8.4. toString không thay đổi builder thành String

Sau lời gọi toString, builder vẫn là StringBuilder và vẫn có thể sửa. Muốn giữ kết quả, phải dùng giá trị String được trả về. Gọi toString rồi bỏ kết quả không tự thay kiểu biến hoặc “đóng” builder.

Cũng không nên gọi toString trong mỗi lượt lặp chỉ để tiếp tục xây dựng, vì mỗi giá trị String yêu cầu một kết quả ổn định tại thời điểm đó. Chỉ tạo các bản kết quả trung gian khi thực sự cần chúng.

## 9. Thực hành

1. Chuyển dòng tạo snapshot xuống sau alias.append("!"). Dự đoán snapshot sẽ chứa Java 21!, rồi chạy đối chiếu.
2. Thay StringBuilder alias = builder bằng new StringBuilder(builder). Hai builder khi ấy độc lập; alias.append("!") không còn sửa builder ban đầu.
3. Gọi buildSummary với mảng rỗng. Theo đúng hợp đồng hiện tại của ví dụ, kết quả là "Steps: " với dấu cách cuối. Nếu yêu cầu sản phẩm khác, sửa quy tắc tạo tiêu đề có chủ đích.
4. Đổi khai báo builder trong main thành final. Các phép append và setLength vẫn hợp lệ; thử gán builder sang đối tượng mới để thấy sự khác biệt.
5. Viết hàm nhận ba trường tùy chọn, chỉ thêm dấu phân cách giữa các trường thật sự có mặt. Giữ builder trong hàm và trả String.
6. So sánh một cách tự xây bằng builder với String.join cho danh sách chỉ cần dấu phẩy. Chọn cách thể hiện hợp đồng dữ liệu rõ hơn, không chọn theo giả định rằng nhiều dòng mã hơn sẽ nhanh hơn.

Tiêu chí nắm bài là phân biệt được đối tượng bất biến với biến được gán lại, biết ai có quyền sửa builder và hiểu thời điểm chuyển bản nháp thành giá trị String kết quả.
