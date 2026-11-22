# Chọn String, StringBuilder hoặc StringBuffer theo nhu cầu

Trong Java, cả ba kiểu đều liên quan đến chuỗi ký tự, nhưng khác nhau về **khả năng thay đổi nội dung**, **chi phí khi nối nhiều lần** và **đồng bộ hóa khi có nhiều luồng**. Việc chọn loại phù hợp phải dựa vào vòng đời dữ liệu và cách sử dụng thực tế.

## 1. Bảng so sánh nhanh

| Tiêu chí | String | StringBuilder | StringBuffer |
|---|---|---|---|
| Nội dung đối tượng thay đổi được? | Không (immutable) | Có (mutable) | Có (mutable) |
| Nối chuỗi thường dùng | +, concat(), formatted() | append(), insert() | append(), insert() |
| Chỉnh sửa tại chỗ | Không | Có | Có |
| Bảo đảm khi nhiều luồng cùng chỉnh sửa một đối tượng | Không có thao tác chỉnh sửa nội dung; có thể chia sẻ giá trị bất biến | Không đồng bộ hóa | Các phương thức thao tác chính được synchronized |
| Trường hợp phù hợp | Giá trị văn bản đã hoàn chỉnh, ít phép nối | Xây dựng văn bản lặp lại trong một luồng | Thực sự phải cùng sửa một bộ đệm từ nhiều luồng và cách đồng bộ từng phương thức đáp ứng yêu cầu |

Quy tắc thực hành: **String cho giá trị thông thường, StringBuilder cho quá trình lắp ráp nhiều bước, StringBuffer khi thật sự cần bộ đệm mutable được đồng bộ hóa**. Một ứng dụng chạy nhiều luồng vẫn có thể dùng StringBuilder nếu mỗi luồng sở hữu một instance riêng.

## 2. String: dữ liệu bất biến

String là immutable: sau khi tạo, nội dung của một **đối tượng String** không thay đổi. concat(), replace(), substring(), toUpperCase() trả về giá trị String; chúng không sửa đối tượng gốc. Biến có thể trỏ sang chuỗi khác, nhưng đó là thay tham chiếu.

~~~java
String original = "Java";
String extended = original.concat(" 17");

System.out.println(original); // Java
System.out.println(extended); // Java 17
~~~

Gọi original.concat(" 17") rồi bỏ qua kết quả sẽ không làm original có thêm " 17". Muốn cập nhật biến, dùng original = original.concat(" 17") hoặc tạo biến mới.

Tính bất biến giúp chia sẻ **nội dung String** an toàn giữa các luồng. Tuy nhiên, nếu các luồng cùng ghi và đọc một trường tham chiếu String hoặc cấu trúc bao quanh nó, quy tắc hiển thị và đồng bộ của Java vẫn áp dụng; tính bất biến không tự làm toàn bộ chương trình thread-safe.

Chọn String khi:

- Biểu diễn tên, mã định danh, câu thông báo, giá trị được truyền giữa các phương thức.
- Ghép ít đoạn bằng biểu thức rõ ràng như "Hello, " + name.
- Trả về giá trị đã hoàn chỉnh và không muốn đối tượng bị sửa nội dung sau đó.
- So sánh nội dung bằng equals(), equalsIgnoreCase() hay phương thức phù hợp.

**Không kết luận rằng mọi phép + đều kém hiệu năng.** Trình biên dịch và JVM hiện đại có tối ưu cho phép nối trong một biểu thức. Từ Java 9, lời gọi nối thường được tạo bằng invokedynamic; cách tối ưu cụ thể tùy phiên bản và ngữ cảnh. Một biểu thức nối ngắn thường dễ đọc hơn việc tự tạo bộ đệm.

Điểm cần tránh là **cộng dồn String lặp đi lặp lại** trong quá trình xây dựng kết quả dài: mỗi lần tạo một giá trị String mới có thể cần sao chép nội dung tích lũy. Với các chuỗi lớn hoặc vòng lặp nhiều lần, hãy cân nhắc StringBuilder.

## 3. StringBuilder: lắp ráp văn bản qua nhiều bước

StringBuilder có bộ đệm mutable. append(), insert(), delete(), replace(), reverse() thay đổi trạng thái cùng đối tượng, giúp giảm nhu cầu tạo String trung gian khi thêm nhiều phần.

~~~java
StringBuilder builder = new StringBuilder("Java");
builder.append(" ").append(17);
builder.insert(4, " Core");
System.out.println(builder); // Java Core 17
~~~

toString() tạo một **String kết quả ổn định**. Nếu builder được chỉnh sửa sau đó, String đã nhận từ toString() không đổi.

~~~java
String snapshot = builder.toString();
builder.append("!");
System.out.println(snapshot); // Java Core 17
System.out.println(builder);  // Java Core 17!
~~~

Khi tạo chuỗi có dấu phân cách qua nhiều lượt, đặt builder **ngoài** vòng lặp:

~~~java
StringBuilder line = new StringBuilder();
for (int i = 1; i <= 3; i++) {
    if (i > 1) {
        line.append(", ");
    }
    line.append(i);
}
System.out.println(line.toString()); // 1, 2, 3
~~~

Một bộ đệm được tái sử dụng thường phù hợp hơn việc thực hiện result = result + fragment qua nhiều vòng lặp. Kết luận về hiệu năng phải dựa trên workload thực tế: kích thước dữ liệu, tối ưu JIT và cách triển khai có thể làm kết quả khác nhau.

**length() và capacity():** length() là độ dài nội dung hiện có theo đơn vị mã UTF-16; capacity() là dung lượng bộ đệm đang cấp phát theo cùng đơn vị, có thể lớn hơn length(). Khi ước lượng được kích thước, new StringBuilder(expectedCapacity) có thể giảm số lần mở rộng bộ đệm; không cần dùng nó cho mọi trường hợp. Một ký tự Unicode ngoài BMP có thể chiếm hai đơn vị mã UTF-16, nên length() không nhất thiết bằng số ký tự người dùng nhìn thấy.

StringBuilder **không đồng bộ hóa** các thao tác. Nếu nhiều luồng cùng chỉnh sửa một instance không có cơ chế phối hợp, kết quả có thể sai. Dùng builder cục bộ trong mỗi thread/task là cách phổ biến để tránh chia sẻ trạng thái mutable.

## 4. StringBuffer: bộ đệm có đồng bộ hóa phương thức

StringBuffer cũng có append(), insert(), delete(), replace() và toString(), nhưng các phương thức thao tác chính được đồng bộ hóa trên đối tượng. Vì vậy các lời gọi append() riêng lẻ vào cùng StringBuffer không giẫm lên nhau như khi nhiều luồng cùng sửa StringBuilder không bảo vệ.

~~~java
StringBuffer buffer = new StringBuffer("Log");
buffer.append(": ").append("ready");
System.out.println(buffer); // Log: ready
~~~

Ví dụ chạy độc lập với hai luồng cùng nối vào một bộ đệm:

~~~java
public class SharedBufferDemo {
    public static void main(String[] args) throws InterruptedException {
        StringBuffer shared = new StringBuffer();

        Runnable task = () -> {
            for (int i = 0; i < 1_000; i++) {
                shared.append("x");
            }
        };

        Thread first = new Thread(task);
        Thread second = new Thread(task);
        first.start();
        second.start();

        first.join();
        second.join();
        System.out.println(shared.length());
    }
}
~~~

Lưu tệp **SharedBufferDemo.java**, biên dịch và chạy bằng JDK 17+:

~~~bash
javac SharedBufferDemo.java
java SharedBufferDemo
~~~

Kết quả:

~~~text
2000
~~~

Mỗi luồng thêm 1.000 ký tự "x"; join() bảo đảm cả hai kết thúc trước khi đọc độ dài. Thứ tự thao tác giữa các luồng không được xác định, nhưng độ dài cuối là 2.000 trong ví dụ này.

**Cảnh báo về tính nguyên tử:** Một phương thức synchronized chỉ bảo vệ **một lời gọi phương thức**. Nếu bài toán yêu cầu kiểm tra điều kiện rồi thêm ký tự như một thao tác duy nhất, đoạn sau không bảo đảm tính nguyên tử khi nhiều luồng cùng làm:

~~~java
if (shared.length() < 2_000) {
    shared.append("x");
}
~~~

Cả length() và append() đều được đồng bộ riêng, nhưng một luồng khác có thể chen vào giữa. Khi bắt buộc giữ nguyên tử cho cả nhóm, dùng cùng monitor:

~~~java
synchronized (shared) {
    if (shared.length() < 2_000) {
        shared.append("x");
    }
}
~~~

Những nơi khác thực hiện cùng quy tắc kiểm tra/cập nhật phải phối hợp trên cùng khóa. Với quy trình nhiều bước phức tạp, cân nhắc giảm hoặc loại bỏ việc dùng chung bộ đệm, thay vì mặc định StringBuffer giải quyết tất cả vấn đề đồng thời.

**Không chọn StringBuffer chỉ vì ứng dụng là đa luồng.** Nếu dữ liệu được tạo riêng trong mỗi tác vụ, StringBuilder không cần chi phí đồng bộ; nếu cần dữ liệu tổng hợp phức tạp từ nhiều luồng, có thể thiết kế kết quả cục bộ rồi hợp nhất theo một bước điều phối.

## 5. Chương trình so sánh hoàn chỉnh (Java 17+)

Ví dụ này độc lập với SharedBufferDemo ở trên. Lưu thành **StringChoiceDemo.java**:

~~~java
public class StringChoiceDemo {
    public static void main(String[] args) {
        String original = "Java";
        String changed = original.concat(" 17");
        System.out.println("original=" + original);
        System.out.println("changed=" + changed);

        StringBuilder builder = new StringBuilder("Java");
        builder.append(" ").append(17);
        System.out.println("builder=" + builder);
        builder.insert(4, " Core");

        String snapshot = builder.toString();
        builder.append("!");
        System.out.println("snapshot=" + snapshot);
        System.out.println("builder now=" + builder);
        System.out.println("content equals="
                + snapshot.equals("Java Core 17"));

        StringBuffer buffer = new StringBuffer("A");
        buffer.append("B").append("C");
        System.out.println("buffer=" + buffer);

        StringBuilder numbers = new StringBuilder();
        for (int i = 1; i <= 3; i++) {
            if (i > 1) {
                numbers.append(", ");
            }
            numbers.append(i);
        }
        System.out.println("joined=" + numbers);
    }
}
~~~

~~~bash
javac StringChoiceDemo.java
java StringChoiceDemo
~~~

Đầu ra chính xác:

~~~text
original=Java
changed=Java 17
builder=Java 17
snapshot=Java Core 17
builder now=Java Core 17!
content equals=true
buffer=ABC
joined=1, 2, 3
~~~

original không đổi sau concat(); builder thay đổi tại chỗ qua append()/insert(); snapshot giữ giá trị String riêng sau khi builder sửa tiếp; buffer minh họa API của StringBuffer. Ví dụ thứ hai chỉ cho thấy thao tác của StringBuffer, còn SharedBufferDemo minh họa dùng chung giữa nhiều luồng.

## 6. Áp dụng theo tình huống

| Nhu cầu | Nên bắt đầu bằng | Lý do |
|---|---|---|
| Tạo thông báo "Xin chào" + tên một lần | String | Đơn giản, dễ đọc |
| Lưu/trao đổi giá trị văn bản hoàn chỉnh | String | Nội dung bất biến |
| Ghép hàng nghìn trường dữ liệu trong một luồng | StringBuilder | Tái sử dụng một bộ đệm khi nối nhiều lần |
| Mỗi tác vụ song song tự tạo một đoạn báo cáo | StringBuilder riêng trong mỗi tác vụ | Không có mutable state chia sẻ |
| Nhiều luồng cùng append vào cùng một bộ đệm | StringBuffer, nếu cần chia sẻ thật sự | Đồng bộ hóa từng lời gọi append |
| Kiểm tra rồi cập nhật cùng bộ đệm ở nhiều luồng | Khóa bao cả nhóm thao tác hoặc thiết kế khác | Đồng bộ từng phương thức chưa đủ |
| Nối các từ bằng dấu phẩy | String.join() hoặc StringJoiner | Diễn đạt trực tiếp dấu phân cách |
| Tạo JSON/SQL/HTML có escape hoặc tham số | API chuyên dụng phù hợp | Xử lý cấu trúc, ký tự đặc biệt hoặc tham số an toàn hơn việc ghép tay |

Ví dụ nối với dấu phân cách khi đã có các chuỗi hoàn chỉnh:

~~~java
String names = String.join(", ", "Lan", "Minh", "An");
System.out.println(names); // Lan, Minh, An
~~~

Nếu dữ liệu ở stream, Collectors.joining(", ") cũng giúp thể hiện rõ nhu cầu nối các phần tử. Không nhất thiết phải tự quản lý dấu phân cách bằng StringBuilder cho trường hợp đơn giản.

## 7. Sai lầm thường gặp

1. **Quên nhận giá trị trả về của String.** s.replace("a", "o") không sửa s. Hãy gán s = s.replace("a", "o") hoặc dùng giá trị mới.
2. **Dùng + để tích lũy trong vòng lặp lớn.** Dùng StringBuilder được tạo bên ngoài vòng lặp khi phải ghép nhiều phần.
3. **Tin rằng mọi dấu + đều chậm.** Cách nối trong một biểu thức được JVM tối ưu theo phiên bản/ngữ cảnh; đừng làm mã phức tạp khi chưa có nhu cầu.
4. **Chọn StringBuffer cho builder chỉ dùng ở một luồng.** Đồng bộ hóa khi không cần có thể tăng chi phí.
5. **Cho rằng StringBuffer bảo đảm nguyên tử cho nhiều phương thức liên tiếp.** Kiểm tra và cập nhật hoặc các chuỗi thao tác phối hợp cần khóa bao trọn.
6. **So sánh StringBuilder bằng equals() như String.** StringBuilder không ghi đè equals() để so sánh nội dung kiểu String; có thể dùng a.toString().equals(b.toString()).
7. **Nhầm StringBuilder/StringBuffer với String.** Chúng triển khai CharSequence, nhưng API yêu cầu String cụ thể cần toString().
8. **Nhầm capacity() với length().** Dung lượng dự trữ khác với số đơn vị UTF-16 đã sử dụng.
9. **Đưa cùng StringBuilder cho nhiều thread mà không phối hợp.** Hãy giữ riêng theo tác vụ hoặc thiết kế đồng bộ thích hợp.
10. **Benchmark bằng một vòng lặp ngắn.** Warm-up, JIT, GC và khả năng loại bỏ phép tính làm số đo sai lệch. Nếu tối ưu là mục tiêu thực tế, dùng JMH với workload có ý nghĩa và kết quả được tiêu thụ.

## 8. Cây quyết định đơn giản

1. Văn bản đã hoàn chỉnh hoặc chỉ ghép một vài đoạn? **Dùng String**.
2. Cần nối/chèn/xóa lặp đi lặp lại để tạo kết quả? **Dùng StringBuilder**.
3. Bộ đệm có thật sự được nhiều luồng cùng sửa? **Xét StringBuffer** hoặc một thiết kế giảm chia sẻ mutable state.
4. Nhiều bước phải là một thao tác nguyên tử? **Thiết kế khóa bao toàn bộ bước**; StringBuffer không tự đủ.
5. Xây dựng xong và cần trả dữ liệu ổn định? **Gọi toString()** để nhận String.

Điểm cốt lõi: **String là giá trị bất biến; StringBuilder là bộ đệm xây dựng chuỗi mặc định; StringBuffer là bộ đệm có đồng bộ hóa từng phương thức**. Chọn theo cách sử dụng và phạm vi chia sẻ, không chỉ theo tên API hoặc giả định hiệu năng.
