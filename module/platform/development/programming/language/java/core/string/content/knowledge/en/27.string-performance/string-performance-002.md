# Nối lặp bằng += và tổng lượng dữ liệu phải sao chép trong Java

Toán tử **+=** thường được dùng để nối thêm nội dung vào một biến String. Ví dụ, sau mỗi lượt đọc dữ liệu, chương trình viết **result += part** để bổ sung một đoạn mới. Cách viết ngắn gọn này có thể gây ra lượng công việc rất lớn khi vòng lặp chạy nhiều lần, vì String trong Java **bất biến (immutable)**: không thể mở rộng trực tiếp nội dung String cũ.

Điểm cần phân tích không chỉ là **số lần nối** mà là **tổng độ dài của tất cả các kết quả trung gian được tạo**. Trong mô hình nối tuần tự phải tạo lại tiền tố cũ, chi phí có thể tăng **bậc hai theo số lượt**; StringBuilder giúp xây dựng kết quả dài dần bằng một vùng đệm có thể thay đổi. Bài này trình bày công thức, ví dụ Java 17, các lựa chọn thay thế và giới hạn của mô hình chi phí khi xét JVM thực tế.

## 1. String bất biến và ý nghĩa của phép +=

Trong Java, câu lệnh:

~~~java
result += part;
~~~

về mặt giá trị tương đương với:

~~~java
result = result + part;
~~~

Khi result là String, phép nối tạo giá trị String kết quả, còn String cũ không bị sửa nội dung. Nếu biến khác vẫn giữ tham chiếu đến chuỗi cũ, nó tiếp tục thấy nội dung cũ. Ví dụ sau minh họa trong một phương thức:

~~~java
String original = "Java";
String result = original;
result += " 17";

System.out.println(original); // Java
System.out.println(result);   // Java 17
~~~

Phép nối một lần hay trong một biểu thức ngắn thường không có vấn đề nghiêm trọng; vấn đề xuất hiện khi **kết quả của lượt trước tiếp tục được đưa vào phép nối ở lượt sau**:

~~~java
String result = "";
for (int i = 0; i < n; i++) {
    result += "x";
}
~~~

Vòng lặp có n lượt; nhưng khi chuỗi dài dần, lượng dữ liệu cần tạo cho mỗi kết quả cũng dài dần. Không thể chỉ nhìn n lượt rồi suy ra toàn bộ công việc là O(n).

## 2. Mô hình sao chép tiền tố khi nối lặp

Giả sử mỗi lượt thêm đúng một ký tự x, bắt đầu từ chuỗi rỗng. Xét **mô hình triển khai đơn giản**: mỗi lượt nối tạo ra một chuỗi mới chứa toàn bộ tiền tố cũ và ký tự mới.

| Lượt | Chuỗi kết quả | Độ dài chuỗi mới | Tổng độ dài đã tạo |
| ---: | --- | ---: | ---: |
| 1 | x | 1 | 1 |
| 2 | xx | 2 | 3 |
| 3 | xxx | 3 | 6 |
| 4 | xxxx | 4 | 10 |
| 5 | xxxxx | 5 | 15 |

Sau n lượt, độ dài chuỗi cuối cùng chỉ là n, nhưng tổng độ dài của các giá trị kết quả sau từng phép nối là:

\[
T(n)=1+2+3+\cdots+n=\frac{n(n+1)}{2}.
\]

Vì vậy **T(n) = Θ(n²)** nếu mỗi lượt phải tái tạo toàn bộ String kết quả. Ví dụ **10.000 lượt** thì String cuối dài 10.000 ký tự, còn tổng độ dài các kết quả trung gian theo mô hình là:

\[
T(10\,000)=\frac{10\,000 \times 10\,001}{2}=50\,005\,000.
\]

Con số **50.005.000 đơn vị ký tự** là kết quả **phân tích toán học**, không phải số byte đã đo được trên máy. Java không quy định số byte vật lý phải copy trong từng phép nối; compiler và JVM có thể tối ưu quá trình này. Công thức cho thấy tại sao việc tạo lại tiền tố dài dần có nguy cơ kém hiệu quả ở quy mô lớn.

### Chỉ tính phần chuỗi cũ

Nếu chỉ tính lượng **tiền tố cũ** cần giữ lại khi nối, lần lượt có 0, 1, 2, ..., n - 1 đơn vị ký tự:

\[
P(n)=0+1+2+\cdots+(n-1)=\frac{n(n-1)}{2}.
\]

Thêm một ký tự mới ở mỗi lượt cho tổng cộng n đơn vị, ta được P(n) + n = T(n). Hai công thức mô tả hai cách đếm khác nhau: **chỉ tiền tố cũ** so với **toàn bộ kết quả mới**.

## 3. Ví dụ Java 17 kiểm chứng phép tính

Tạo tệp **RepeatedConcatDemo.java**:

~~~java
public class RepeatedConcatDemo {
    public static void main(String[] args) {
        int n = 5;
        String joined = "";
        long sumLengths = 0;

        for (int i = 0; i < n; i++) {
            joined += "x";
            sumLengths += joined.length();
        }

        StringBuilder builder = new StringBuilder(n);
        for (int i = 0; i < n; i++) {
            builder.append('x');
        }
        String built = builder.toString();

        System.out.println("+= result: " + joined);
        System.out.println("builder result: " + built);
        System.out.println("equal: " + joined.equals(built));
        System.out.println("sum lengths: " + sumLengths);
        System.out.println("formula: " + ((long) n * (n + 1) / 2));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 RepeatedConcatDemo.java
java RepeatedConcatDemo
~~~

Kết quả:

~~~text
+= result: xxxxx
builder result: xxxxx
equal: true
sum lengths: 15
formula: 15
~~~

Biến **sumLengths** cộng độ dài chuỗi sau mỗi lượt. Nó chỉ kiểm tra công thức 1 + 2 + ... + n; **đây không phải phép đo số byte JVM đã cấp phát/copy**. Hai cách xây dựng cho kết quả cùng nội dung, nhưng có chiến lược sử dụng vùng nhớ khác nhau. Ép n thành long trước phép nhân giúp tránh tràn int trong những ví dụ n vừa phải; với n sát giới hạn int nên ép cả n + 1 sang long.

## 4. Nếu mỗi lượt thêm một phần có độ dài khác nhau

Thực tế, một vòng lặp có thể ghép từng dòng, từng trường JSON hay những phần văn bản có kích thước không đều. Gọi **a_i** là độ dài phần thêm ở lượt i, **S_i** là độ dài toàn bộ kết quả sau lượt đó.

\[
S_i=a_1+a_2+\cdots+a_i.
\]

Khi mô hình đòi tái tạo String kết quả trong mỗi lượt, tổng độ dài các kết quả trung gian là:

\[
T=\sum_{i=1}^{n}S_i
 = n a_1 +(n-1)a_2+\cdots+1a_n.
\]

Hay tương đương:

\[
T=\sum_{j=1}^{n}(n-j+1)a_j.
\]

Đây là cách nhìn **theo từng phần dữ liệu**: phần thêm vào sớm xuất hiện trong nhiều kết quả trung gian về sau hơn phần thêm ở cuối. Nếu mỗi phần dài k ký tự, tổng độ dài là:

\[
T=k\frac{n(n+1)}{2}.
\]

Khi k là hằng số, đây vẫn là **Θ(n²) theo số lượt n**. Nếu phần có độ dài thay đổi, phải chỉ rõ biến nào đang được dùng để phân tích độ phức tạp.

Ví dụ ba phần **A**, **BB**, **CCC** có độ dài 1, 2, 3. Các kết quả lũy tiến dài 1, 3, 6, nên T = 1 + 3 + 6 = **10**, dù String cuối chỉ dài **6**.

### Mô hình và số byte thực tế có giống nhau?

Không nhất thiết. T(n) đếm các **đơn vị ký tự** trong kết quả trung gian theo mô hình. Java String có thể dùng biểu diễn **Latin-1 hoặc UTF-16** tùy dữ liệu và JVM, JIT có thể tránh một số thao tác trung gian, và chi phí có cả quản lý đối tượng lẫn garbage collection.

Do đó không nên khẳng định mỗi phép **+=** luôn copy đúng một số byte bằng công thức trên. Kết luận hợp lý là: **nối lặp mà thực sự phải tạo lại String dài dần có nguy cơ tăng chi phí bậc hai**. Chi phí máy thật cần được đo trên JDK, máy và workload cụ thể.

## 5. StringBuilder xử lý chuỗi dài dần như thế nào?

**StringBuilder** là một bộ dựng chuỗi có nội dung thay đổi được. Khi gọi **append(part)**, nó cố gắng thêm dữ liệu vào vùng lưu trữ đang có, thay vì tạo một String bất biến chứa toàn bộ tiền tố ở mỗi lượt:

~~~java
StringBuilder builder = new StringBuilder();
for (String part : parts) {
    builder.append(part);
}
String result = builder.toString();
~~~

Đây là đoạn mã minh họa; biến parts phải được khai báo ở chương trình thực tế.

StringBuilder có hai khái niệm:

- **length():** số đơn vị char trong nội dung hiện có.
- **capacity():** sức chứa hiện tại trước khi cần mở rộng vùng lưu trữ.

Nếu vùng chứa đủ, append có thể thêm vào mà không cần tạo lại toàn bộ tiền tố. Khi thiếu dung lượng, builder có thể phải cấp vùng mới và copy nội dung cũ. Với chiến lược mở rộng theo tỷ lệ, chi phí mở rộng có thể được phân bổ (**amortized**), làm tổng công việc xây chuỗi thường gần tuyến tính theo tổng dữ liệu được thêm vào. Không cần giả định append là O(1) trong mọi trường hợp: thêm một chuỗi có độ dài m vẫn phải xử lý m đơn vị dữ liệu.

Khi ước lượng trước kích thước đầu ra, có thể khởi tạo:

~~~java
StringBuilder builder = new StringBuilder(estimatedLength);
~~~

Tham số ở đây là **capacity**, không phải nội dung/length. Một builder mới với capacity 1000 vẫn có length() == 0. Ước lượng vừa phải giúp hạn chế việc mở rộng; ước lượng quá lớn có thể gây lãng phí bộ nhớ.

Quan trọng: thông thường hãy **gọi builder.toString() một lần sau vòng lặp**. Nếu gọi toString() ở mỗi lượt để lấy snapshot, chi phí tạo những chuỗi tiền tố dài dần vẫn có thể đạt mức bậc hai vì yêu cầu đầu ra của chính bài toán đã lớn.

## 6. Ví dụ StringBuilder hoàn chỉnh với dấu phân cách

Tạo tệp **BuilderJoinDemo.java**:

~~~java
public class BuilderJoinDemo {
    public static void main(String[] args) {
        String[] parts = {"A", "BB", "CCC"};
        StringBuilder builder = new StringBuilder(12);

        for (int i = 0; i < parts.length; i++) {
            if (i > 0) {
                builder.append(" | ");
            }
            builder.append(parts[i]);
        }

        String result = builder.toString();
        System.out.println(result);
        System.out.println("length: " + result.length());
        System.out.println("capacity >= length: "
                + (builder.capacity() >= builder.length()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 BuilderJoinDemo.java
java BuilderJoinDemo
~~~

~~~text
A | BB | CCC
length: 12
capacity >= length: true
~~~

Ba phần chứa 1 + 2 + 3 = 6 ký tự; hai dấu phân cách ** | ** chứa 3 ký tự mỗi dấu, nên độ dài tổng cộng là 12. Builder được cấp capacity 12 phù hợp với ví dụ. Dòng cuối kiểm tra quan hệ capacity >= length, không phụ thuộc công thức tăng capacity nội bộ của một phiên bản JDK.

Khi chỉ cần nối các chuỗi với một dấu phân cách, **String.join(" | ", parts)** thường ngắn và rõ nghĩa hơn vòng lặp thủ công. Với stream có thể dùng **Collectors.joining(" | ")**; chọn phương thức thể hiện rõ ý định thay vì viết nhiều thao tác append nếu không cần thiết.

## 7. Khi nào Java tối ưu toán tử +?

Trong Java 9+, trình biên dịch Java có thể triển khai các biểu thức nối chuỗi qua **invokedynamic** và **StringConcatFactory**; JVM có thể tối ưu thêm ở runtime. Một biểu thức nối một số phần cố định, ví dụ:

~~~java
String label = "ID=" + id + "; status=" + status;
~~~

không nên bị mặc định xem là chuỗi các phép cấp phát vô ích. Java hiện đại có thể xây kết quả rất hiệu quả. Với phần nhỏ và biểu thức đơn giản, toán tử **+** thường là lựa chọn dễ đọc, hợp lý.

Nhưng vòng lặp:

~~~java
String result = "";
for (String part : parts) {
    result += part;
}
~~~

đưa **giá trị từ lượt trước** vào lượt sau. Nếu ở mỗi lượt chuỗi tăng dần phải được tái tạo, tổng lượng kết quả trung gian tuân theo công thức ở phần đầu. JVM có thể tối ưu một số trường hợp cụ thể, nhưng **ngôn ngữ không bảo đảm việc nối lặp này luôn được chuyển thành một bộ đệm tái sử dụng**. Vì vậy, với lượng dữ liệu lớn hoặc số vòng lặp phụ thuộc đầu vào, StringBuilder là giải pháp rõ ràng và ổn định hơn.

**Đừng thay mọi phép + bằng StringBuilder thủ công:** tiêu chí đúng là có bao nhiêu lượt, độ dài kết quả tăng ra sao, biểu thức có thật sự nằm trên đường thực thi nóng hay không, và người đọc mã có hiểu rõ ý định không.

## 8. Đo thời gian và bộ nhớ đúng cách

Không nên dựng hai đoạn code nhỏ, đo mỗi đoạn một lần bằng **System.nanoTime()**, rồi coi đó là kết luận tuyệt đối. Thời gian chạy phụ thuộc JIT warm-up, garbage collector, trạng thái CPU, số liệu đầu vào và việc compiler có thể loại bỏ công việc nếu kết quả không được dùng.

Khi phải xác minh hiệu năng thực tế:

1. Dùng **cùng dữ liệu đầu vào** và kiểm tra **đầu ra giống nhau**.
2. Warm-up mã được đo, chạy nhiều lần.
3. Không tính thời gian **println**, đọc tệp hay tạo dữ liệu vào phép đo nối chuỗi.
4. Thử nhiều giá trị **n** và kích thước mỗi part, thay vì một con số đơn lẻ.
5. Dùng **JMH** khi cần benchmark tin cậy; quan sát throughput, allocations và GC.
6. Phân biệt **thời gian thực**, **số byte cấp phát** và **tổng độ dài tiền tố theo công thức**.

Ví dụ đoạn văn bản chứa Unicode: String.length() đếm **đơn vị UTF-16**, không nhất thiết bằng số ký tự người dùng nhìn thấy. Điều đó càng cho thấy không thể lấy phép đếm ký tự làm số byte copy vật lý mà không kiểm tra thêm.

## 9. Tình huống áp dụng

| Nhu cầu | Lựa chọn thường phù hợp | Vì sao |
| --- | --- | --- |
| Nối vài phần cố định trong một biểu thức | Dùng + | Cú pháp gọn, JVM tối ưu biểu thức hiệu quả. |
| Xây một String dài qua nhiều vòng | Dùng StringBuilder | Tái sử dụng vùng đệm, hạn chế tạo lại tiền tố dài dần. |
| Ghép danh sách có delimiter | String.join hoặc StringBuilder | Thể hiện rõ quy tắc dấu phân cách. |
| Ghép stream thành một chuỗi | Collectors.joining | Diễn đạt phép gom các phần tử. |
| Các luồng độc lập đều xây chuỗi | Mỗi tác vụ một StringBuilder | StringBuilder không đồng bộ, tránh chia sẻ mutable state. |
| Thật sự cần bộ đệm đồng bộ hóa | Cân nhắc StringBuffer hoặc giải pháp đồng bộ phù hợp | StringBuffer đồng bộ hóa phương thức nhưng không thay cho thiết kế đồng bộ toàn bộ quy trình. |
| Cần String kết quả ở mỗi lượt | Chấp nhận chi phí snapshot | Tổng độ dài **mọi đầu ra bắt buộc** vốn có thể rất lớn. |

## 10. Những lỗi thường gặp

| Nhầm lẫn | Giải thích và cách sửa |
| --- | --- |
| N phép nối luôn là O(n). | Mỗi lượt có thể phải xử lý tiền tố dài dần; hãy tính **tổng độ dài kết quả**. |
| Mọi phép + với String đều là O(n²). | Độ phức tạp phụ thuộc dạng code; biểu thức cố định có thể được tối ưu. |
| Công thức T(n) là số byte cấp phát chính xác. | Đây là mô hình tổng độ dài kết quả, không phải phép đo vật lý. |
| StringBuilder không bao giờ copy dữ liệu cũ. | Khi mở rộng capacity, nó có thể phải copy vùng chứa. |
| new StringBuilder(1000) tạo 1000 ký tự. | Số 1000 là capacity ban đầu, length vẫn bằng 0. |
| Gọi builder.toString() ở mọi vòng vẫn rẻ. | Mỗi snapshot là kết quả String; tổng kích thước các snapshot có thể bậc hai. |
| Dùng StringBuffer luôn nhanh hơn vì có đồng bộ. | Đồng bộ có chi phí; bộ đệm cục bộ thường dùng StringBuilder. |
| Đo một lần với nanoTime là đủ. | JIT/GC/CPU gây nhiễu; dùng phép đo có warm-up, nhiều mẫu hoặc JMH. |
| Nối String từ nhiều luồng bằng một StringBuilder chung là an toàn. | StringBuilder không bảo đảm thread safety; tách theo tác vụ hoặc đồng bộ đúng cách. |

## 11. Bài tự kiểm tra

**Câu 1.** Với 8 lần thêm một ký tự, theo mô hình tái tạo toàn bộ String, tổng độ dài các kết quả trung gian là bao nhiêu?

Đáp án: **8 × 9 / 2 = 36**. Chuỗi cuối chỉ dài 8; tổng độ dài **tiền tố cũ** là 7 × 8 / 2 = **28**.

**Câu 2.** Nối ba phần có độ dài 2, 1, 3 theo thứ tự. Tổng độ dài các kết quả sau mỗi lượt là bao nhiêu?

Đáp án: ba độ dài lũy tiến là 2, 3, 6; tổng **11**. Theo công thức trọng số: 3 × 2 + 2 × 1 + 1 × 3 = 11.

**Câu 3.** Nếu dùng StringBuilder để tạo kết quả cuối một lần nhưng trong từng lượt vẫn phải xuất ra bản sao toàn bộ tiền tố, có còn tránh được mọi chi phí bậc hai không?

Đáp án: **không**. Yêu cầu tạo ra n snapshot với độ dài tăng dần đã có tổng kích thước đầu ra theo mô hình là Θ(n²).

**Câu 4.** Với một biểu thức ghép họ, tên và lời chào, nên ưu tiên toán tử + hay StringBuilder?

Đáp án: **toán tử +** thường đủ rõ ràng và hiệu quả trong biểu thức ngắn; không cần tối ưu thủ công khi chưa có bằng chứng về nút thắt.

## 12. Kết luận

Khi thấy **result += part bên trong vòng lặp**, hãy hỏi không chỉ “lặp bao nhiêu lần?” mà còn “**String kết quả tăng dài như thế nào?**”. Với n phần một ký tự và mô hình tái tạo chuỗi mới ở mọi lượt, tổng độ dài các kết quả trung gian bằng **n(n + 1) / 2**, tức tăng bậc hai theo n, trong khi kết quả cuối chỉ dài n. Với phần dài không đều, tổng chi phí mô hình là tổng độ dài các tiền tố.

**StringBuilder** cho phép ghi thêm vào vùng đệm thay đổi được, mở rộng khi cần và tạo String kết quả khi hoàn tất; đây là lựa chọn phổ biến để nối dài trong vòng lặp. **Dấu +** vẫn phù hợp với biểu thức nối ngắn. Mô hình chi phí giúp lựa chọn thiết kế hợp lý, còn hiệu năng thật của chương trình cần được đánh giá bằng công cụ đo trên dữ liệu thực tế.