# Ngữ nghĩa ghi và đọc trường volatile

## Khái niệm: một điểm đồng bộ hóa cho việc chia sẻ trạng thái

`volatile` là từ khóa có thể đặt trên một field instance hoặc static để quy định ngữ nghĩa truy cập trường đó giữa các luồng.

Một cách dùng điển hình là cờ trạng thái:

```java
private volatile boolean ready;
```

Nhưng ý nghĩa không dừng ở việc “luồng khác thấy giá trị mới”. Ghi và đọc cùng một trường volatile còn tham gia vào quan hệ đồng bộ hóa của Mô hình bộ nhớ Java (Java Memory Model, JMM). Nhờ đó, một luồng có thể dùng một lần ghi volatile để công bố các thao tác đã thực hiện trước nó cho luồng đọc phù hợp.

Cần phân biệt ba câu hỏi:

- **Khả năng quan sát:** một luồng được phép thấy giá trị nào?
- **Thứ tự:** những thao tác nào được bảo đảm xảy ra-trước theo mô hình bộ nhớ?
- **Tính nguyên tử:** một thao tác hay một chuỗi thao tác có bị xen kẽ bởi luồng khác không?

`volatile` giải quyết một số yêu cầu ở hai câu hỏi đầu và tính nguyên tử của từng lần truy cập trường. Nó không biến toàn bộ phương thức hoặc một phép cập nhật nhiều bước thành vùng loại trừ lẫn nhau.

Các ngữ nghĩa này vẫn áp dụng trong Java hiện đại; ví dụ trong bài chạy trên JDK 17 trở lên.

## Quy tắc trung tâm: ghi volatile xảy ra-trước các lần đọc tiếp theo phù hợp

JMM quy định một lần ghi vào trường volatile đồng bộ-hóa-với các lần đọc tiếp theo của cùng trường đó theo thứ tự đồng bộ hóa. Quan hệ này tạo ra một cạnh **happens-before** giữa việc ghi và đọc.

Ví dụ về một giao thức công bố một lần:

```java
// Các field của cùng một đối tượng chia sẻ:
int answer;
volatile boolean ready;

// Luồng ghi:
answer = 42;
ready = true;

// Luồng đọc:
if (ready) {
    System.out.println(answer);
}
```

Đây là mảnh minh họa, chưa phải chương trình đầy đủ. Giả sử:

- Ban đầu `ready` là false.
- Chỉ luồng ghi nói trên đổi `ready` thành true.
- `answer` không còn bị sửa sau khi được công bố.
- Luồng đọc thực sự quan sát được giá trị true từ giao thức đó.

Khi ấy có chuỗi quan hệ:

```text
Ghi answer = 42
      |
      | thu tu chuong trinh trong luong ghi
      v
Ghi volatile ready = true
      |
      | synchronizes-with
      v
Doc volatile ready thay true
      |
      | thu tu chuong trinh trong luong doc
      v
Doc answer
```

Nhờ tính bắc cầu của happens-before, phép ghi `answer = 42` xảy ra-trước phép đọc `answer` ở nhánh đã quan sát ready.

Dù `answer` không phải volatile, dữ liệu vẫn được công bố qua cờ volatile đúng cách. Không cần biến mọi field dữ liệu thành volatile chỉ để sử dụng mô hình một lần công bố này.

Cơ sở đặc tả: [JLS §17.4.5](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html#jls-17.4.5).

## “Đọc giá trị mới nhất” cần hiểu theo mô hình bộ nhớ

Nói “volatile luôn đọc giá trị mới nhất” có thể gây hiểu nhầm nếu hiểu là một bảo đảm theo thời gian đồng hồ hoặc theo điều mà người quan sát bên ngoài mong đợi.

Nếu luồng đọc chạy trước khi luồng ghi thực hiện `ready = true`, nó có thể đọc false. `volatile` không làm thao tác ghi xảy ra sớm hơn, không buộc luồng ghi được lập lịch ngay và không dự đoán một giá trị chưa được ghi.

Ý nghĩa phải gắn với thứ tự của các hành động đồng bộ hóa trên cùng biến và các quy tắc JMM, thay vì giả định mọi luồng đang cùng chạy ở một khoảnh khắc tuyệt đối.

Điều thực hành cần giữ:

- Đọc đúng trường volatile được dùng để công bố.
- Chỉ dựa vào dữ liệu công bố sau khi đã quan sát tín hiệu phù hợp.
- Không dùng việc “đã đợi một lúc lâu” thay cho quan hệ đồng bộ hóa.

Không cần và không nên giải thích tính đúng bằng khẳng định “mọi lần đọc đều bỏ qua cache và đọc RAM”. JMM quy định hành vi được quan sát; JVM và phần cứng có thể thực hiện bằng các cơ chế tối ưu khác nhau miễn giữ đúng ngữ nghĩa.

## Ngữ nghĩa ghi: công bố những gì ở phía trước trong giao thức

Trong mô hình công bố:

```java
answer = 42;
ready = true;
```

thứ tự này có ý nghĩa. Dữ liệu được hoàn tất trước khi tín hiệu sẵn sàng được công bố.

Đảo thành:

```java
// Cố ý minh họa giao thức sai:
ready = true;
answer = 42;
```

không tạo cạnh happens-before từ phép ghi `answer` phía sau tới một luồng chỉ đọc thấy ready true. Luồng đọc có thể đi vào nhánh trước khi phép gán answer được thực hiện.

Không thể khắc phục bằng câu nói “cờ là volatile rồi nên dữ liệu nào cũng sẽ thấy”. Phải vẽ đúng đường happens-before cho thao tác dữ liệu đang xét.

Một lần ghi volatile có thể được xem như điểm công bố trong cách dùng này. Nó không thay cho việc xây dựng đối tượng hoàn chỉnh hoặc giữ đúng thứ tự các câu lệnh của giao thức.

## Ngữ nghĩa đọc: dữ liệu phải được dùng sau khi đã nhận tín hiệu

Luồng đọc cần quan sát cờ trước khi dùng dữ liệu được công bố:

```java
if (ready) {
    int snapshot = answer;
}
```

Mảnh trên minh họa thứ tự có ý nghĩa. Nếu đọc dữ liệu trước:

```java
int snapshot = answer;
if (ready) {
    System.out.println(snapshot);
}
```

thì `snapshot` đã được lấy trước lần đọc volatile. Việc sau đó thấy ready true không quay ngược thời gian để cập nhật lại biến cục bộ đó.

Khi giải thích bằng “release/acquire”, cần giữ đúng hai phía: ghi để công bố, đọc tín hiệu để tiếp nhận, cùng với thứ tự trong từng luồng. Đây là một cách hiểu hữu ích, nhưng các truy cập volatile còn thuộc thứ tự đồng bộ hóa của JMM; không nên thay thế toàn bộ đặc tả bằng một khẩu hiệu.

## Chương trình đầy đủ: công bố một giá trị qua cờ volatile

Lưu thành `VolatilePublicationDemo.java`:

```java
public class VolatilePublicationDemo {
    static final class State {
        int answer;
        volatile boolean ready;
    }

    public static void main(String[] args) throws InterruptedException {
        State state = new State();

        Thread reader = new Thread(() -> {
            long deadline = System.nanoTime() + 5_000_000_000L;
            while (!state.ready) {
                if (System.nanoTime() - deadline >= 0) {
                    System.out.println("timeout");
                    return;
                }
                Thread.onSpinWait();
            }
            System.out.println("answer=" + state.answer);
        });

        Thread writer = new Thread(() -> {
            state.answer = 42;
            state.ready = true;
        });

        reader.start();
        writer.start();
        writer.join();
        reader.join();
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 VolatilePublicationDemo.java
java VolatilePublicationDemo
```

Trong lượt chạy bình thường khi luồng ghi được thực hiện trước hạn chờ của luồng đọc:

```text
answer=42
```

Chương trình có hạn chờ năm giây để tránh một ví dụ chờ bận không có giới hạn. Nếu luồng đọc hết hạn trước khi quan sát ready, nó có thể in:

```text
timeout
```

Lựa chọn timeout là điều kiện của bộ thử nghiệm, không phải phát biểu rằng volatile bảo đảm một thời hạn lập lịch. Điểm được JMM bảo đảm ở nhánh thành công là: sau khi luồng đọc quan sát ready true theo giao thức một lần công bố, nó đọc answer là 42.

Chương trình không dùng một `sleep` để cố tạo thứ tự giữa luồng đọc và ghi.

## Vì sao ví dụ không cần answer là volatile?

`State` được tạo trước khi các luồng bắt đầu. Sau đó:

- Luồng ghi gán `answer = 42`, rồi ghi ready true.
- Luồng đọc lặp lại việc đọc ready.
- Chỉ sau khi thấy true, luồng đọc mới đọc answer.
- Không có thao tác ghi mới vào answer sau điểm công bố.

Cờ volatile là điểm đồng bộ hóa để chuyển giao dữ liệu. Đây là trường hợp khác với việc có nhiều luồng tùy ý đọc/ghi answer trong suốt vòng đời đối tượng.

Các lời gọi `join` trong main được dùng để đợi hai luồng kết thúc. Chúng không thay cho phép đọc ready trong luồng đọc và không phải lý do để luồng đọc được phép thấy answer tại vị trí đang xét.

`Thread.onSpinWait()` chỉ cung cấp gợi ý khi luồng đang chờ bận. Nó không tự tạo quan hệ happens-before cho answer, không thay cho volatile và không bảo đảm luồng ghi được lập lịch. Xem [Thread.onSpinWait](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html#onSpinWait()).

## Tính nguyên tử: từng lần đọc/ghi khác với thao tác ghép

Một lần đọc hoặc ghi volatile là thao tác nguyên tử tương ứng. Với `long` và `double`, volatile cũng giữ yêu cầu đọc/ghi nguyên tử của trường theo quy tắc JMM.

Nhưng:

```java
volatile int count;

// Nhiều luồng cùng thực hiện:
count++;
```

không làm toàn bộ phép tăng trở thành nguyên tử.

Có thể hình dung `count++` cần:

1. Đọc giá trị hiện tại.
2. Tính giá trị cộng một.
3. Ghi giá trị mới.

Một tình huống hợp lệ khi count bắt đầu bằng 0:

| Bước | Luồng A | Luồng B |
| --- | --- | --- |
| 1 | Đọc 0 | |
| 2 | | Đọc 0 |
| 3 | Ghi 1 | |
| 4 | | Ghi 1 |

Kết quả là 1, dù có hai lần tăng. Từng lần đọc/ghi riêng lẻ vẫn tuân thủ volatile; lỗi nằm ở chuỗi đọc-sửa-ghi không được bảo vệ như một thao tác.

Nếu cần tăng nguyên tử, có thể dùng `AtomicInteger.incrementAndGet()` hoặc một cơ chế khóa phù hợp. Không coi `volatile` là cách thay một bộ đếm đồng bộ. API nguyên tử được mô tả tại [AtomicInteger](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html).

Tương tự, chuỗi “nếu chưa khởi tạo thì khởi tạo” hoặc “nếu còn chỗ thì thêm” không tự thành nguyên tử chỉ vì một field liên quan là volatile.

## Tham chiếu volatile không làm mọi nội dung đối tượng thành volatile

Ví dụ:

```java
volatile int[] values = new int[1];
```

`volatile` áp dụng cho field tham chiếu `values`, không tự áp dụng cho từng phần tử của mảng.

- Gán `values = newArray` là ghi volatile vào tham chiếu.
- Đọc `values` là đọc volatile của tham chiếu.
- Ghi `values[0] = 10` không phải một lần ghi volatile vào phần tử mảng.

Tương tự, `volatile Holder current` không tự biến mọi field của `Holder` thành trường volatile. Nó có thể giúp công bố dữ liệu được chuẩn bị trước khi gán tham chiếu, nhưng các thay đổi sau đó của đối tượng vẫn cần một giao thức đồng bộ hóa phù hợp.

Cách dùng thường dễ lý giải là tạo một ảnh chụp trạng thái hoàn chỉnh, không sửa nó sau khi công bố, rồi thay toàn bộ tham chiếu volatile.

Nếu cần đọc nhiều thông tin từ cùng một ảnh chụp, có thể lấy tham chiếu một lần vào biến cục bộ rồi dùng nó. Đọc lại field volatile nhiều lần có thể nhận các ảnh chụp khác nhau nếu luồng ghi đã thay tham chiếu giữa các lần đọc.

`volatile` không tự tạo một giao dịch nguyên tử cho toàn bộ đồ thị đối tượng.

## Giao thức cờ một lần không tự mở rộng thành bộ truyền dữ liệu nhiều lần

Ví dụ của bài chỉ công bố một giá trị và chuyển ready từ false sang true một lần.

Nếu liên tục sửa answer nhưng giữ ready luôn true, một lần đọc true sau đó không tự chứng minh nó gắn với phiên bản answer nào mà người đọc đang kỳ vọng.

Nếu đổi ready false/true nhiều lần mà không có quy tắc nhận phiên bản và phối hợp rõ ràng, luồng đọc có thể bỏ lỡ các lần chuyển trạng thái hoặc không phân biệt được hai lần true khác nhau.

Với giao tiếp lặp lại, cần thiết kế thêm:

- Cách nhận diện phiên bản hoặc phần tử dữ liệu.
- Quyền sở hữu và thời điểm được sửa.
- Cách tránh ghi đè dữ liệu chưa được tiêu thụ.
- Cách chờ và xử lý việc hoàn tất.

Hàng đợi đồng thời, khóa, điều kiện chờ hoặc một cơ chế trao đổi dữ liệu phù hợp thường biểu diễn bài toán này rõ hơn một cờ boolean tự chế. `volatile` là một thành phần đồng bộ hóa, không phải toàn bộ giao thức.

## Cờ dừng: chỉ giúp quan sát yêu cầu, không cưỡng chế luồng dừng

Một trường hợp phù hợp khác là:

```java
volatile boolean stopRequested;
```

Luồng làm việc định kỳ đọc cờ và tự kết thúc khi thấy yêu cầu dừng. Đây là dừng hợp tác.

`volatile` không:

- Ngắt ngay một thao tác I/O đang bị chặn.
- Đánh thức tự động một luồng đang đợi trên một cơ chế khác.
- Cưỡng chế kết thúc luồng tại một thời điểm cụ thể.
- Tự thay thế cơ chế interruption nếu tác vụ và API liên quan dùng interruption để hủy.

Vì vậy, chọn cờ dừng còn phụ thuộc công việc có cơ hội đọc cờ đều đặn hay không. Khả năng quan sát cờ và khả năng kết thúc tác vụ là hai phần riêng.

## Phân biệt volatile với khóa và nguyên tử

| Nhu cầu | Volatile có đủ không? |
| --- | --- |
| Công bố dữ liệu đã hoàn tất qua một cờ theo giao thức rõ ràng | Có thể đủ |
| Công bố một tham chiếu tới ảnh chụp không sửa sau công bố | Có thể phù hợp |
| Một luồng ghi cờ dừng, luồng khác định kỳ đọc | Có thể phù hợp cho phần quan sát cờ |
| Nhiều luồng cùng tăng bộ đếm | Không đủ cho phép tăng ghép |
| Cập nhật nhiều field cùng giữ bất biến | Không tự đủ |
| Giữ một đoạn thao tác không bị luồng khác xen kẽ | Không thay thế khóa |
| Đánh thức luồng đang bị chặn hoặc bảo đảm thời hạn | Không cung cấp bảo đảm đó |

Khóa có thể đồng thời cung cấp loại trừ lẫn nhau và quan hệ bộ nhớ phù hợp. Các lớp nguyên tử cung cấp những thao tác cập nhật nguyên tử xác định. Lựa chọn phụ thuộc hợp đồng cần giữ, không chỉ mong muốn “dữ liệu trông mới”.

Cú pháp và ý nghĩa trường volatile được mô tả tại [JLS §8.3.1.4](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.3.1.4).

## Những giới hạn cú pháp và thiết kế

`volatile` là modifier của field, không phải cách khai báo một biến cục bộ hoặc tham số phương thức thành biến chia sẻ có đồng bộ hóa.

Một field cũng không thể vừa `final` vừa `volatile` trong khai báo Java. Hai cơ chế có vai trò khác nhau: final giữ ràng buộc gán và có ngữ nghĩa công bố riêng; volatile dành cho các truy cập trường theo quy tắc đồng bộ hóa.

`volatile` không gắn vào toàn bộ phương thức như `synchronized`, không tự xác định các field khác phải được bảo vệ và không giúp một đối tượng thoát ra giữa quá trình xây dựng trở thành một đối tượng đã được khởi tạo đầy đủ.

## Không dùng sleep hoặc log làm bằng chứng thay thế

Thêm `Thread.sleep`, `yield` hay `onSpinWait` không phải một cách tạo quan hệ công bố cho một field thường.

Việc một chương trình thiếu đồng bộ hóa “chạy đúng” trên máy thử cũng không chứng minh nó đúng theo JMM. Thay đổi JIT, tải hệ thống hoặc phần cứng có thể làm các hành vi khác xuất hiện.

Việc thêm log còn có thể ảnh hưởng lịch chạy hoặc đưa vào những thao tác đồng bộ hóa ở thư viện xuất dữ liệu, khiến một lỗi khó tái hiện hơn. Vì vậy, cần giải thích tính đúng bằng đường happens-before, không bằng số lần chạy ra một output mong muốn.

Trong ví dụ, output của lượt chạy là minh chứng thực hành. Lập luận JMM của nhánh thành công mới là cơ sở bảo đảm giá trị answer khi tín hiệu ready đã được nhận đúng giao thức.

## Lỗi phổ biến và cách đối chiếu

| Hiểu nhầm | Cách kiểm tra |
| --- | --- |
| Volatile tự làm count++ nguyên tử | Tách thao tác đọc, tính và ghi |
| Đọc cờ sau khi đã chụp dữ liệu vẫn sửa được snapshot cũ | Kiểm tra thứ tự trong luồng đọc |
| Ghi cờ trước rồi mới ghi dữ liệu cũng như nhau | Vẽ đường happens-before cho từng thao tác dữ liệu |
| Tham chiếu volatile khiến mọi field con cũng volatile | Xác định chính field nào có modifier |
| Có volatile là bảo đảm luồng khác chạy ngay | Phân biệt ngữ nghĩa bộ nhớ và lập lịch |
| Đã sleep đủ lâu là dữ liệu được công bố | Cần quan hệ đồng bộ hóa thật sự |
| Một cờ true dùng mãi cho mọi phiên bản dữ liệu | Xác định tín hiệu gắn với phiên bản nào |
| Cờ dừng tự đánh thức tác vụ bị chặn | Kiểm tra cơ chế hủy và điểm đọc cờ |

## Thực hành kiểm chứng

1. Chạy chương trình, phân biệt output thành công với điều kiện timeout của bộ thử nghiệm.
2. Vẽ chuỗi happens-before từ `answer = 42` đến phép đọc answer sau vòng lặp.
3. Trên một bản sao minh họa, đảo hai câu lệnh của luồng ghi. Giải thích vì sao phép đọc 0 không còn bị lập luận công bố ban đầu loại trừ; không yêu cầu một lượt chạy nhất định phải tái hiện nó.
4. Tách một thí nghiệm bộ đếm volatile có nhiều luồng tăng. Giải thích cơ chế mất cập nhật bằng lịch xen kẽ, dù một số lượt chạy có thể tình cờ đủ tổng.
5. Thay bộ đếm ghép bằng `AtomicInteger.incrementAndGet()` trong thí nghiệm đó rồi so sánh bảo đảm của thao tác.
6. Với một tham chiếu volatile tới đối tượng có nhiều field, xác định field nào được ghi trước công bố và field nào còn bị sửa sau đó.

Điều cần nắm là **ghi volatile có thể công bố thao tác trước nó, đọc phù hợp tiếp nhận sự công bố ấy; từng truy cập nguyên tử không biến cả chuỗi nghiệp vụ thành nguyên tử**.
