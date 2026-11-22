# Thời điểm kiểm tra điều kiện và tạo phần tử kế tiếp trong Stream

Từ Java 9, Stream có overload **iterate(seed, hasNext, next)** để tạo một chuỗi phần tử theo quy tắc lặp và tự kết thúc khi điều kiện không còn đúng. Chủ đề quan trọng của overload này là **thứ tự thực thi**: stream tạo phần tử ứng viên bằng hàm next, kiểm tra ứng viên bằng predicate hasNext, rồi mới đưa ứng viên vào pipeline. Các bước này chỉ diễn ra khi có thao tác terminal yêu cầu phần tử.

Hiểu đúng thời điểm gọi hai hàm giúp dự đoán chính xác phần tử nào được phát ra, khi nào stream dừng và liệu có phần tử nào đã được tạo nhưng không được phát ra hay không.

## 1. Stream xử lý dữ liệu theo cơ chế lazy

Stream trong Java mô tả một pipeline xử lý dữ liệu. Các thao tác trung gian như map, filter, peek, limit thường chỉ xây dựng pipeline; chúng chưa duyệt dữ liệu ngay tại thời điểm được gọi. Việc duyệt bắt đầu khi có thao tác terminal như forEach, toList, reduce, count hoặc findFirst.

Cơ chế này được gọi là **lazy evaluation**. Nó cho phép pipeline chỉ xử lý lượng dữ liệu cần thiết. Những thao tác terminal có khả năng kết thúc sớm như findFirst, anyMatch hoặc limit có thể khiến nguồn chỉ tạo một phần các phần tử.

Với Stream.iterate, điều này có nghĩa là việc gọi phương thức để tạo Stream chưa tự động chạy predicate hay hàm next. Các hàm chỉ được gọi khi pipeline bắt đầu yêu cầu phần tử.

## 2. Overload iterate ba tham số từ Java 9

Chữ ký tổng quát:

~~~java
static <T> Stream<T> iterate(
    T seed,
    Predicate<? super T> hasNext,
    UnaryOperator<T> next
)
~~~

Ba tham số có vai trò:

- **seed:** phần tử bắt đầu của chuỗi.
- **hasNext:** predicate kiểm tra một phần tử ứng viên có được phép xuất hiện trong Stream hay không.
- **next:** hàm tạo phần tử kế tiếp từ phần tử hiện tại, thường trả về một giá trị mới cùng kiểu T.

Stream được trả về là sequential và ordered. Predicate được áp dụng cho seed và từng phần tử kế tiếp trước khi phần tử đó được đưa ra cho pipeline. Khi predicate trả về false, Stream kết thúc. Hàm next không được gọi tiếp sau khi điều kiện đã thất bại.

Overload ba tham số được bổ sung trong Java 9. Nó phù hợp khi muốn tạo một chuỗi có điều kiện dừng rõ ràng ngay tại nguồn, ví dụ sinh các số nguyên từ 1 đến 5.

~~~java
Stream<Integer> numbers =
        Stream.iterate(1, number -> number <= 5, number -> number + 1);
~~~

Kết quả khi duyệt toàn bộ Stream là:

~~~text
1
2
3
4
5
~~~

Điều kiện dùng dấu <= nên phần tử 5 vẫn được phát ra. Khi phần tử ứng viên 6 được tạo, predicate trả về false và Stream kết thúc; 6 không xuất hiện trong kết quả.

## 3. Thứ tự tạo ứng viên, kiểm tra và phát phần tử

Quy trình cần phân biệt ba hành động:

1. **Kiểm tra seed:** khi cần phần tử đầu tiên, Stream gọi hasNext(seed). Nếu kết quả là true, seed được phát ra. Nếu false, Stream rỗng và hàm next chưa được gọi.
2. **Tạo ứng viên kế tiếp:** khi pipeline cần thêm một phần tử, Stream gọi next(current) để tạo ứng viên mới từ phần tử trước đó.
3. **Kiểm tra ứng viên:** Stream gọi hasNext(candidate). Nếu true, ứng viên được phát ra. Nếu false, ứng viên bị loại và Stream kết thúc; hàm next không được gọi tiếp.

Ví dụ với seed là 1, điều kiện number <= 3 và hàm next là number + 1:

| Bước | Hành động | Kết quả |
|---|---|---|
| Đầu tiên | hasNext(1) | true, phát ra 1 |
| Tiếp theo | next(1) tạo 2; hasNext(2) | true, phát ra 2 |
| Tiếp theo | next(2) tạo 3; hasNext(3) | true, phát ra 3 |
| Cuối cùng | next(3) tạo 4; hasNext(4) | false, không phát ra 4 và kết thúc |

Như vậy, khi duyệt hết một chuỗi hữu hạn bằng thao tác terminal cần đọc đến cuối, hàm next có thể tạo ra **một ứng viên cuối cùng không được phát ra**. Ứng viên đó được tạo để predicate kiểm tra xem chuỗi đã kết thúc hay chưa.

Điểm này rất dễ nhầm: predicate kiểm tra phần tử ứng viên trước khi phần tử đó được phát ra. Để có ứng viên tiếp theo, hàm next phải chạy trước; predicate sau đó quyết định ứng viên có được đưa vào Stream hay không.

## 4. Ví dụ chạy được: quan sát thời điểm gọi hai hàm

Lưu chương trình dưới tên **IterateTimingDemo.java**. Ví dụ dùng Java 17 trở lên và ghi lại từng lần gọi hasNext, next để nhìn rõ thứ tự thực thi.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

public class IterateTimingDemo {

    private static Stream<Integer> sequence(List<String> events) {
        return Stream.iterate(
                1,
                value -> {
                    events.add("hasNext(" + value + ")");
                    return value <= 3;
                },
                value -> {
                    int candidate = value + 1;
                    events.add("next(" + value + ") -> " + candidate);
                    return candidate;
                });
    }

    public static void main(String[] args) {
        List<String> fullEvents = new ArrayList<>();
        Stream<Integer> fullStream = sequence(fullEvents);

        System.out.println("after creation: " + fullEvents);
        List<Integer> fullValues = fullStream.toList();

        System.out.println("values: " + fullValues);
        fullEvents.forEach(System.out::println);

        List<String> limitedEvents = new ArrayList<>();
        List<Integer> limitedValues =
                sequence(limitedEvents).limit(3).toList();

        System.out.println("limited values: " + limitedValues);
        limitedEvents.forEach(System.out::println);

        List<String> firstEvents = new ArrayList<>();
        Integer firstValue = sequence(firstEvents).findFirst().orElse(-1);

        System.out.println("first value: " + firstValue);
        firstEvents.forEach(System.out::println);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 IterateTimingDemo.java
java IterateTimingDemo
~~~

Kết quả stdout:

~~~text
after creation: []
values: [1, 2, 3]
hasNext(1)
next(1) -> 2
hasNext(2)
next(2) -> 3
hasNext(3)
next(3) -> 4
hasNext(4)
limited values: [1, 2, 3]
hasNext(1)
next(1) -> 2
hasNext(2)
next(2) -> 3
hasNext(3)
first value: 1
hasNext(1)
~~~

Giải thích từng phần:

- **after creation: []** chứng minh việc gọi sequence để tạo Stream chưa chạy predicate hay hàm next.
- Khi gọi toList(), pipeline duyệt đến khi predicate trả về false. Vì vậy, sau khi phát ra 3, hàm next tạo 4 và hasNext(4) kiểm tra rồi kết thúc. Giá trị 4 không có trong danh sách kết quả.
- Với limit(3), pipeline chỉ yêu cầu ba phần tử. Predicate được kiểm tra cho 1, 2 và 3; hàm next chỉ cần tạo 2 và 3. Không có yêu cầu phần tử thứ tư nên 4 không được tạo.
- Với findFirst(), pipeline chỉ cần phần tử đầu tiên. Stream kiểm tra hasNext(1), phát ra 1 và dừng; hàm next không được gọi.

Các side effect ghi vào danh sách events chỉ nhằm quan sát thứ tự thực thi trong ví dụ học tập. Trong ứng dụng thực tế, nên giữ predicate và hàm next stateless, không phụ thuộc vào side effect để quyết định kết quả.

## 5. Nhu cầu duyệt, terminal operation và short-circuit

Số lần gọi hasNext và next phụ thuộc vào lượng phần tử mà pipeline cần. Các thao tác terminal có thể yêu cầu duyệt toàn bộ hoặc dừng ngay khi đã có đủ kết quả. Lưu ý: `limit(n)` là intermediate operation có tính short-circuiting, không phải terminal operation. Nó giới hạn số phần tử pipeline cần từ nguồn; một terminal operation phía sau (ví dụ `toList()` hoặc `forEach()`) mới kích hoạt việc duyệt và có thể dừng khi đã nhận đủ n phần tử.

| Thao tác | Nhu cầu duyệt | Hệ quả với iterate |
|---|---|---|
| toList() | Duyệt đến khi nguồn kết thúc | Có thể tạo ứng viên cuối cùng bị predicate loại |
| forEach() | Duyệt toàn bộ | Tiếp tục tạo và kiểm tra cho đến khi predicate false |
| limit(n) + terminal operation | Terminal operation chỉ cần tối đa n phần tử | Sau khi đủ n phần tử, pipeline có thể dừng yêu cầu thêm từ nguồn |
| findFirst() | Chỉ cần phần tử đầu tiên | Nếu seed hợp lệ, next chưa cần chạy |
| anyMatch() | Dừng khi tìm thấy phần tử thỏa điều kiện | Có thể chỉ tạo một phần chuỗi |
| noneMatch() | Dừng khi predicate trả về true cho một phần tử; khi đó kết quả là false | Có thể không duyệt hết nguồn |

Ví dụ, nếu Stream được tạo bằng điều kiện number <= 100 nhưng pipeline chỉ gọi limit(5), nguồn chỉ cần tạo và kiểm tra năm phần tử đầu. Không cần tạo phần tử thứ sáu để chứng minh điều kiện kết thúc của chuỗi.

Nếu predicate của iterate dừng trước khi đủ n phần tử, limit(n) chỉ trả về số phần tử thực tế có trong nguồn. limit không tự tạo thêm phần tử để đạt đủ số lượng.

Một lưu ý quan trọng: Stream là single-use. Sau khi một terminal operation đã tiêu thụ Stream, không thể dùng lại chính đối tượng Stream đó cho terminal operation khác. Nếu cần chạy lại ví dụ với một trace mới, hãy gọi hàm tạo Stream để nhận một Stream mới.

## 6. So sánh overload hai tham số và ba tham số

Stream có hai overload iterate hiện hành thường gặp:

~~~java
Stream<Integer> unbounded =
        Stream.iterate(1, number -> number + 1);

Stream<Integer> bounded =
        Stream.iterate(1, number -> number <= 5, number -> number + 1);
~~~

- Overload hai tham số nhận seed và hàm next. Nó tạo một Stream tuần tự, có thứ tự và không có điều kiện kết thúc nội tại. Khi cần duyệt hữu hạn, phải giới hạn bằng thao tác như limit.
- Overload ba tham số nhận thêm predicate hasNext. Predicate kiểm soát việc phần tử ứng viên có được phát ra hay không; khi predicate false, nguồn kết thúc.

Ví dụ giới hạn overload hai tham số:

~~~java
Stream.iterate(1, number -> number + 1)
      .limit(5)
      .forEach(System.out::println);
~~~

Kết quả:

~~~text
1
2
3
4
5
~~~

Cả hai overload đều đang được hỗ trợ trong Java hiện hành. Overload ba tham số có từ Java 9 và hữu ích khi điều kiện dừng là một phần tự nhiên của quy tắc sinh dữ liệu.

## 7. Các nguyên tắc khi viết predicate và hàm next

Để Stream có hành vi dễ dự đoán:

- **Predicate phải xác định điều kiện kết thúc:** với chuỗi hữu hạn, cần có thời điểm hasNext trả về false.
- **Hàm next phải tiến triển:** nếu hàm luôn trả lại giá trị cũ và predicate luôn true, Stream sẽ không tự kết thúc.
- **Giữ hàm stateless:** predicate và hàm next nên cho kết quả dựa trên đối số hiện tại, không dựa vào trạng thái thay đổi bên ngoài.
- **Tránh can thiệp nguồn dữ liệu:** không sửa đổi cấu trúc dữ liệu mà pipeline đang dùng để sinh hoặc duyệt phần tử.
- **Chú ý chi phí tạo ứng viên cuối:** khi duyệt đến hết, hàm next có thể chạy thêm một lần để tạo ứng viên bị predicate loại. Nếu việc tạo ứng viên tốn kém hoặc gây side effect, hãy cân nhắc cách thiết kế nguồn dữ liệu.
- **Dùng thao tác giới hạn khi cần:** với nguồn có thể không kết thúc, limit hoặc một terminal operation short-circuit phù hợp giúp tránh duyệt vô hạn.

## 8. Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ predicate kiểm tra phần tử hiện tại để quyết định có gọi next hay không | Hiểu sai thứ tự tạo ứng viên và kiểm tra | next tạo ứng viên kế tiếp trước; hasNext kiểm tra ứng viên đó trước khi phát ra |
| Nghĩ ứng viên bị loại sẽ không được tạo | Bỏ sót một lần gọi next khi duyệt hết nguồn hữu hạn | Nhớ rằng ứng viên cuối có thể đã được tạo rồi mới bị predicate loại |
| Mong hàm chạy ngay khi gọi Stream.iterate | Cho rằng không có trace nghĩa là API không hoạt động | Stream lazy; cần terminal operation để bắt đầu duyệt |
| Dùng predicate luôn true cho chuỗi không có giới hạn | Nguồn không tự kết thúc | Đặt điều kiện dừng hoặc giới hạn bằng limit |
| Dùng lại cùng một Stream sau terminal operation | Gặp IllegalStateException hoặc hành vi không hợp lệ theo vòng đời Stream | Tạo Stream mới từ nguồn hoặc từ hàm factory |
| Dùng side effect làm logic chính trong next hoặc hasNext | Kết quả khó kiểm soát, khó kiểm thử và phụ thuộc thứ tự duyệt | Dùng hàm stateless và không can thiệp dữ liệu nguồn |

## 9. Ghi nhớ

- Stream.iterate(seed, hasNext, next) là overload có từ Java 9 để tạo Stream tuần tự có điều kiện dừng.
- Khi cần seed, Stream kiểm tra hasNext(seed) trước khi phát seed.
- Khi cần phần tử tiếp theo, Stream gọi next(current) để tạo ứng viên rồi kiểm tra hasNext(candidate).
- Ứng viên chỉ được phát ra nếu predicate trả về true. Nếu false, Stream kết thúc và ứng viên đó không xuất hiện trong kết quả.
- Stream lazy: tạo pipeline chưa gọi predicate hoặc next; terminal operation mới kích hoạt việc duyệt.
- Short-circuit như limit hoặc findFirst có thể dừng trước khi tạo ứng viên mà một lần duyệt toàn bộ sẽ cần.
- Khi duyệt hết nguồn hữu hạn, có thể có một ứng viên cuối được tạo nhưng không được phát ra.
