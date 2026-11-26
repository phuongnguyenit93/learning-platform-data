# Dùng biến không tên trong vòng lặp khi chỉ cần tác dụng phụ hoặc số lần lặp

## Mục tiêu

Trong một vòng lặp, đôi khi chương trình cần thực hiện một hành động cho mỗi phần tử hoặc chỉ cần đếm số phần tử. Giá trị của phần tử hiện tại không được dùng trong thân vòng lặp. Khai báo một biến có tên trong trường hợp này dễ khiến người đọc nghĩ rằng thân vòng lặp sẽ sử dụng giá trị đó.

Từ Java 22, có thể dùng dấu gạch dưới `_` để khai báo biến không tên. Với enhanced `for`, cách viết này thể hiện rõ rằng vòng lặp vẫn nhận từng phần tử nhưng chương trình cố ý bỏ qua giá trị của nó.

Tính năng Unnamed Variables and Patterns được hoàn thiện trong Java 22 theo JEP 456. Đây là tính năng chính thức, không cần bật preview. JLS hiện hành vẫn cho phép khai báo biến không tên trong câu lệnh `for`.

## Bỏ qua phần tử khi chỉ cần thực hiện tác dụng phụ

Giả sử ứng dụng nhận một danh sách các dòng dữ liệu và cần ghi nhận một lần tiến trình đã đi qua mỗi dòng. Nếu không cần đọc nội dung dòng, tên biến như `line` là thừa:

~~~java
static void recordVisits(Iterable<String> lines, Runnable recordVisit) {
    for (String line : lines) {
        recordVisit.run();
    }
}
~~~

Thân vòng lặp không sử dụng `line`. Có thể thay biến đó bằng biến không tên:

~~~java
static void recordVisits(Iterable<String> lines, Runnable recordVisit) {
    for (String _ : lines) {
        recordVisit.run();
    }
}
~~~

Dấu `_` nói rõ rằng mỗi phần tử được lấy ra chỉ để duy trì một lần lặp. Tác dụng phụ nằm trong thân vòng lặp, còn giá trị phần tử không cần thiết.

Có thể dùng `var` nếu muốn trình biên dịch suy luận kiểu phần tử:

~~~java
static void recordVisits(Iterable<String> lines, Runnable recordVisit) {
    for (var _ : lines) {
        recordVisit.run();
    }
}
~~~

Dùng kiểu tường minh như `String _` khi kiểu phần tử giúp người đọc hiểu dữ liệu đang được duyệt. Dùng `var _` khi kiểu đã rõ từ biểu thức ở vế phải và việc lặp lại kiểu không giúp ích.

## Đếm số phần tử mà không cần đặt tên cho từng phần tử

Một trường hợp phổ biến là đếm số phần tử của một mảng hoặc một `Iterable`, trong khi không cần giữ lại hay kiểm tra giá trị từng phần tử.

~~~java
static int countElements(Iterable<?> elements) {
    int total = 0;

    for (Object _ : elements) {
        total++;
    }

    return total;
}
~~~

Mỗi lượt lặp nhận một phần tử tiếp theo và tăng `total`. Biến không tên giúp tập trung vào điều chương trình thực sự cần: số lượt phần tử đã được duyệt.

Với mảng hoặc collection có sẵn thuộc tính/phương thức lấy kích thước, hãy ưu tiên cách đọc trực tiếp đó:

~~~java
int arrayCount = orderIds.length;
int listCount = orders.size();
~~~

Vòng lặp hữu ích khi đầu vào chỉ cung cấp `Iterable` và không có cách lấy số lượng trực tiếp. Khi đó, việc đếm cần duyệt qua các phần tử, có độ phức tạp tuyến tính theo số phần tử. Hãy cân nhắc rằng việc duyệt có thể tiêu thụ iterator, kích hoạt thao tác đọc dữ liệu hoặc không kết thúc nếu nguồn là vô hạn.

## Biến không tên trong vòng for thông thường

Java cũng cho phép khai báo biến không tên trong phần khởi tạo của basic `for`. Trường hợp này hữu ích khi một biểu thức khởi tạo có tác dụng phụ nhưng trả về giá trị mà chương trình không cần dùng.

~~~java
static int logLoopStart() {
    System.out.println("Bắt đầu vòng lặp");
    return 0;
}

static void runThreeTimes() {
    for (int i = 0, _ = logLoopStart(); i < 3; i++) {
        System.out.println("Thực hiện công việc");
    }
}
~~~

Ở đây:

- `i` là biến có tên vì điều kiện và biểu thức cập nhật cần đọc, thay đổi nó.
- `logLoopStart()` được gọi đúng một lần khi khởi tạo vòng lặp.
- Giá trị trả về của `logLoopStart()` được gán cho biến không tên và bị bỏ qua.
- Thân vòng lặp chạy ba lần.

Đây là cách dùng hẹp. Nếu chỉ muốn gọi một phương thức trước vòng lặp, có thể gọi nó ở một câu lệnh riêng trước vòng `for`; không cần tạo biến không tên chỉ để làm mã ngắn hơn. Ví dụ trên minh họa khả năng của ngôn ngữ khi biểu thức khởi tạo cần nằm cùng khai báo với biến điều khiển.

## Không dùng _ làm biến đếm

Biến không tên không thể được tham chiếu trong biểu thức. Vì vậy, đoạn mã sau không hợp lệ:

~~~java
// Lỗi biên dịch: không thể đọc hoặc cập nhật biến không tên.
for (int _ = 0; _ < 10; _++) {
    performTask();
}
~~~

Nếu cần một bộ đếm để điều khiển vòng lặp, hãy giữ tên biến:

~~~java
for (int i = 0; i < 10; i++) {
    performTask();
}
~~~

Trong ví dụ này, `i` không phải biến thừa: điều kiện `i < 10` và biểu thức `i++` cần tham chiếu đến nó. Biến không tên chỉ phù hợp khi giá trị được khởi tạo nhưng không cần được đọc hoặc cập nhật bằng tên trong mã.

## Khi nào nên dùng?

| Tình huống | Cách viết phù hợp | Lý do |
|---|---|---|
| Duyệt từng phần tử nhưng thân vòng lặp không cần giá trị phần tử | `for (Order _ : orders)` | Nói rõ phần tử được cố ý bỏ qua. |
| Đếm phần tử của một `Iterable` không có API lấy kích thước | `for (Object _ : elements) total++` | Chỉ cần số lượt duyệt, không cần tên phần tử. |
| Gọi một biểu thức khởi tạo có tác dụng phụ và bỏ qua giá trị trả về trong basic `for` | `int i = 0, _ = initialize()` | Thể hiện giá trị trả về không được sử dụng. |
| Dùng chỉ số để truy cập phần tử hoặc điều khiển số lượt lặp | Dùng biến có tên như `i` | Điều kiện hoặc thân vòng lặp cần đọc biến đó. |
| Xử lý nội dung từng phần tử | Dùng biến có tên như `order` | Thân vòng lặp cần giá trị phần tử. |

## Những quy tắc cần nhớ

- Chỉ dấu gạch dưới đơn `_` mới là tên dành riêng cho biến không tên. `_item` vẫn là một tên biến bình thường.
- Biến không tên có thể được khởi tạo nhưng không thể được tham chiếu trong mã nguồn.
- Trong enhanced `for`, biến không tên vẫn được khởi tạo bằng từng phần tử theo thứ tự duyệt; thân vòng lặp vẫn chạy một lần cho mỗi phần tử.
- Nếu cần dùng giá trị phần tử, hãy đặt tên có ý nghĩa cho biến.
- Nếu mảng hoặc collection đã cung cấp số lượng qua `length` hoặc `size()`, thường nên dùng trực tiếp thay vì duyệt chỉ để đếm.
- Tính năng này đã là một phần chính thức của Java từ JDK 22. Không cần `--enable-preview` khi biên dịch hoặc chạy chương trình dùng biến không tên.

## Kết luận

Dùng `_` trong vòng lặp khi phần tử được lấy ra chỉ để duy trì lượt lặp, thực hiện tác dụng phụ hoặc đếm số phần tử. Cách viết này giúp mã thể hiện rõ ý định bỏ qua giá trị. Khi biến tham gia điều kiện, biểu thức cập nhật hoặc xử lý dữ liệu trong thân vòng lặp, hãy tiếp tục dùng một tên biến có ý nghĩa.

## Tài liệu tham khảo

- [JEP 456 – Unnamed Variables & Patterns](https://openjdk.org/jeps/456)
- [Oracle Java 22 – Unnamed Variables and Patterns](https://docs.oracle.com/en/java/javase/22/language/unnamed-variables-and-patterns.html)
- [Java Language Specification, Java SE 26 – Declarations and the for Statement](https://docs.oracle.com/en/java/javase/26/docs/specs/jls26.pdf)
- [Oracle Java 26 – Java Language Changes Summary](https://docs.oracle.com/en/java/javase/26/language/java-language-changes-summary.html)

