# Ảnh hưởng của thứ tự duyệt và chế độ song song trong Stream

## Mục tiêu

Java Stream mô tả một chuỗi thao tác trên dữ liệu. Khi xử lý một Stream, cần phân biệt hai khái niệm:

- **Encounter order (thứ tự gặp):** thứ tự logic của các phần tử do nguồn dữ liệu hoặc các thao tác trước đó xác định.
- **Execution order (thứ tự thực thi):** thời điểm và thứ tự các thao tác thực sự chạy trên các luồng thực thi.

Hai thứ tự này không nhất thiết giống nhau. Một parallel Stream có thể xử lý các phần tử theo nhiều thứ tự và trên nhiều thread, nhưng vẫn tạo ra kết quả theo encounter order nếu nguồn có thứ tự và thao tác kết thúc yêu cầu bảo toàn thứ tự.

Hiểu rõ sự khác biệt này giúp tránh lỗi khi dùng forEach, findFirst, findAny, limit, takeWhile, dropWhile và các thao tác song song.

## 1. Encounter order là gì?

Encounter order là thứ tự mà Stream trình bày các phần tử cho pipeline. Thứ tự này thường xuất phát từ nguồn dữ liệu:

- List có encounter order theo thứ tự phần tử trong danh sách.
- Mảng có thứ tự theo chỉ số.
- Stream tạo từ một dãy số có thứ tự theo dãy đó.
- HashSet không bảo đảm một encounter order ổn định.
- TreeSet duyệt theo thứ tự của comparator hoặc thứ tự tự nhiên.

Ví dụ với List:

~~~java
List<Integer> numbers = List.of(4, 1, 3, 2);

List<Integer> result = numbers.stream()
        .map(number -> number * 10)
        .toList();

System.out.println(result);
~~~

Kết quả:

~~~text
[40, 10, 30, 20]
~~~

Thao tác map thay đổi giá trị nhưng không làm mất encounter order của Stream. Vì vậy, kết quả vẫn theo thứ tự 4, 1, 3, 2 của List ban đầu.

Một số thao tác có thể thiết lập hoặc thay đổi thứ tự:

- sorted() tạo thứ tự theo comparator hoặc thứ tự tự nhiên.
- unordered() loại bỏ ràng buộc encounter order của Stream.
- Các thao tác trung gian như map và filter thông thường bảo toàn encounter order nếu nguồn có thứ tự.

Không nên suy luận rằng mọi nguồn Stream đều có thứ tự. Nếu nguồn không định nghĩa encounter order, chương trình không được dựa vào một thứ tự duyệt cụ thể.

## 2. Sequential Stream và Parallel Stream

### Sequential Stream

Sequential Stream thực hiện pipeline theo chế độ tuần tự:

~~~java
List<Integer> result = numbers.stream()
        .map(number -> number * 2)
        .toList();
~~~

Các phần tử được xử lý trong một luồng thực thi của pipeline tại một thời điểm. Với nguồn có encounter order, kết quả của các thao tác bảo toàn thứ tự sẽ giữ thứ tự đó.

### Parallel Stream

Parallel Stream cho phép pipeline chia công việc thành các phần để xử lý song song:

~~~java
List<Integer> result = numbers.parallelStream()
        .map(number -> number * 2)
        .toList();
~~~

Các phần tử có thể được xử lý trên nhiều thread. Một phần tử xuất hiện sau trong nguồn có thể được xử lý xong trước một phần tử đứng trước.

Tuy nhiên, với nguồn có encounter order và thao tác kết thúc yêu cầu thứ tự, kết quả vẫn được ghép theo encounter order. Ví dụ, toList() trên một Stream có thứ tự giữ thứ tự gặp của các phần tử, kể cả khi pipeline chạy song song.

**Điểm cần nhớ:** parallel() thay đổi chế độ thực thi, không tự động xóa encounter order. Việc xử lý song song cũng không bảo đảm chương trình chạy nhanh hơn; chi phí chia việc, đồng bộ và ghép kết quả có thể lớn hơn lợi ích đối với dữ liệu nhỏ hoặc thao tác quá nhẹ.

## 3. forEach và forEachOrdered

Hai thao tác đều thực hiện hành động với từng phần tử, nhưng có cam kết khác nhau về thứ tự.

### forEach

forEach không bảo đảm thứ tự encounter order khi chạy trên parallel Stream có thứ tự:

~~~java
numbers.parallelStream()
        .forEach(System.out::println);
~~~

Các hành động có thể được thực hiện trên nhiều thread và theo thứ tự bất kỳ. Vì vậy, không dựa vào thứ tự dòng được in để biểu diễn thứ tự ban đầu.

Với sequential Stream, forEach thường xử lý theo thứ tự duyệt của pipeline, nhưng API không đưa ra cam kết thứ tự rõ ràng như forEachOrdered. Nếu chương trình cần một cam kết rõ ràng về encounter order thì hãy dùng forEachOrdered.

### forEachOrdered

forEachOrdered thực hiện hành động theo encounter order nếu Stream có thứ tự:

~~~java
numbers.parallelStream()
        .forEachOrdered(System.out::println);
~~~

Dù pipeline là parallel, hành động cuối cùng vẫn được thực hiện theo thứ tự gặp. Hành động với một phần tử xảy ra trước hành động với phần tử tiếp theo theo quan hệ happens-before được quy định cho thao tác này.

forEachOrdered có thể giảm khả năng thực thi song song ở giai đoạn tiêu thụ kết quả, vì các hành động phải tuân theo thứ tự. Hãy chỉ dùng khi thứ tự hành động thực sự quan trọng.

| Thao tác | Sequential Stream | Parallel Stream có encounter order |
|---|---|---|
| forEach | Thường theo thứ tự duyệt, nhưng không có cam kết thứ tự như forEachOrdered | Không bảo đảm encounter order |
| forEachOrdered | Theo encounter order | Bảo đảm encounter order |

Nếu Stream không có encounter order, forEachOrdered cũng không thể khôi phục một thứ tự ban đầu vốn không tồn tại.

## 4. findFirst và findAny

Hai thao tác đều tìm một phần tử phù hợp với pipeline, nhưng khác nhau về cam kết thứ tự.

### findFirst

findFirst trả về phần tử đầu tiên theo encounter order nếu Stream có thứ tự:

~~~java
Optional<Integer> first = numbers.parallelStream().findFirst();
~~~

Với List chứa 4, 1, 3, 2, kết quả là 4. Trong parallel Stream, việc bảo đảm tìm phần tử đầu tiên có thể cần phối hợp giữa các phần xử lý.

### findAny

findAny trả về một phần tử bất kỳ:

~~~java
Optional<Integer> any = numbers.parallelStream().findAny();
~~~

Không có cam kết rằng kết quả phải là phần tử đầu tiên. Kết quả có thể thay đổi giữa các lần chạy hoặc cách thực thi, đặc biệt trong chế độ song song.

findAny phù hợp khi chương trình chỉ cần một phần tử thỏa điều kiện và không quan tâm phần tử đó đứng ở vị trí nào.

| Tiêu chí | findFirst | findAny |
|---|---|---|
| Bảo đảm phần tử đầu tiên | Có, nếu Stream có encounter order | Không |
| Có thể dùng parallel Stream | Có | Có |
| Ràng buộc thứ tự | Cao hơn khi phải xác định phần tử đầu tiên | Linh hoạt hơn |
| Khi phù hợp | Cần đúng phần tử đầu tiên | Chỉ cần một phần tử phù hợp bất kỳ |

Cả hai trả về Optional. Nếu Stream rỗng, kết quả là Optional.empty().

## 5. unordered() và ảnh hưởng đến các thao tác có trạng thái

unordered() trả về một Stream tương đương về các phần tử nhưng không còn cam kết encounter order. Nó không xáo trộn dữ liệu theo một thuật toán cụ thể và cũng không tự biến Stream thành parallel.

Ví dụ:

~~~java
long count = numbers.parallelStream()
        .unordered()
        .limit(2)
        .count();
~~~

Kết quả count là 2 nếu nguồn có đủ phần tử. Hai phần tử được chọn không được bảo đảm là hai phần tử đầu tiên của List.

Khi thứ tự không quan trọng, loại bỏ ràng buộc thứ tự có thể giúp một số thao tác song song giảm chi phí phối hợp. Tuy nhiên, unordered() chỉ nên được dùng khi mọi kết quả được chấp nhận đều đúng với yêu cầu nghiệp vụ.

### limit và skip

Với Stream có thứ tự:

- limit(n) giữ tối đa n phần tử đầu tiên theo encounter order.
- skip(n) bỏ qua n phần tử đầu tiên theo encounter order.

Trên ordered parallel Stream, hai thao tác này có thể cần phối hợp để xác định chính xác phần đầu của chuỗi, làm giảm hiệu năng.

Sau unordered(), chương trình không còn yêu cầu chọn hoặc bỏ đúng các phần tử đầu theo thứ tự nguồn. Điều này có thể cho phép thực thi song song hiệu quả hơn, nhưng tập phần tử cụ thể có thể khác.

## 6. takeWhile và dropWhile trong Java 9+

Java 9 bổ sung takeWhile và dropWhile cho Stream. Đây là các thao tác hữu ích khi xử lý phần đầu của một chuỗi theo điều kiện.

Với Stream có encounter order:

- takeWhile(predicate) giữ lại phần tiền tố dài nhất mà mọi phần tử đều thỏa predicate; dừng tại phần tử đầu tiên không thỏa.
- dropWhile(predicate) bỏ phần tiền tố dài nhất mà mọi phần tử đều thỏa predicate; giữ lại phần còn lại.

Ví dụ:

~~~java
List<Integer> values = List.of(1, 2, 3, 4, 2, 5);

List<Integer> prefix = values.stream()
        .takeWhile(value -> value < 4)
        .toList();

List<Integer> remainder = values.stream()
        .dropWhile(value -> value < 4)
        .toList();

System.out.println(prefix);
System.out.println(remainder);
~~~

Kết quả:

~~~text
[1, 2, 3]
[4, 2, 5]
~~~

Phần tử 4 là phần tử đầu tiên không thỏa điều kiện, nên takeWhile dừng tại đó và dropWhile bắt đầu giữ lại từ đó. Giá trị 2 xuất hiện sau 4 vẫn được giữ vì dropWhile chỉ bỏ tiền tố liên tiếp.

### Khi Stream không có encounter order

Trên unordered Stream, takeWhile và dropWhile không còn ý nghĩa tiền tố theo một thứ tự cố định. Các thao tác có thể chọn hoặc bỏ một tập con các phần tử thỏa điều kiện theo quy tắc của Stream không có thứ tự.

Do đó, nếu yêu cầu là lấy chính xác một đoạn đầu của List, hãy giữ encounter order. Chỉ gọi unordered() khi logic chấp nhận việc chọn hoặc bỏ các phần tử phù hợp mà không cần dựa vào vị trí ban đầu.

Trong parallel Stream có thứ tự, takeWhile và dropWhile có thể tốn chi phí phối hợp để bảo toàn tiền tố. Hãy đo hiệu năng với dữ liệu thực tế trước khi tối ưu.

## 7. Side effects, trạng thái chia sẻ và an toàn luồng

Một lỗi phổ biến là thay đổi một đối tượng dùng chung bên trong thao tác Stream song song:

~~~java
List<Integer> result = new ArrayList<>();

numbers.parallelStream()
        .forEach(result::add); // Không an toàn
~~~

ArrayList không hỗ trợ nhiều thread cùng sửa đổi theo cách này. Kết quả có thể sai, mất phần tử hoặc phát sinh lỗi do truy cập đồng thời.

Hãy ưu tiên các thao tác không có side effect và dùng collector để thu thập kết quả:

~~~java
List<Integer> result = numbers.parallelStream()
        .map(number -> number * 2)
        .toList();
~~~

Với Stream có encounter order, toList() giữ thứ tự gặp. Phương thức Stream.toList() có từ Java 16 và trả về một List không thể sửa đổi.

Nếu cần thu thập theo một cấu trúc khác, dùng collector phù hợp:

~~~java
Set<Integer> unique = numbers.parallelStream()
        .collect(Collectors.toSet());
~~~

Set không cam kết encounter order. Nếu cần kết quả theo thứ tự, hãy chọn cấu trúc hoặc collector phù hợp với yêu cầu, chẳng hạn TreeSet khi cần thứ tự sắp xếp.

### Stateless và non-interfering

Các hàm truyền vào Stream nên:

- **Stateless:** kết quả không phụ thuộc vào trạng thái thay đổi bên ngoài giữa các lần gọi.
- **Non-interfering:** không sửa đổi nguồn dữ liệu của Stream trong lúc pipeline đang xử lý nguồn đó.

Ví dụ không nên dùng bộ đếm bên ngoài trong map:

~~~java
int[] counter = {0};

numbers.parallelStream()
        .map(number -> {
            counter[0]++;
            return number * 2;
        })
        .toList();
~~~

counter[0] được nhiều thread truy cập mà không có đồng bộ. Kết quả có thể không chính xác. Hãy dùng count(), reduce() hoặc collector thích hợp để biểu đạt phép tính.

Cũng không nên dựa vào peek() để bảo đảm một side effect bắt buộc luôn xảy ra. Stream có thể tối ưu pipeline và bỏ qua việc thực hiện một số thao tác trung gian nếu không ảnh hưởng đến kết quả cuối cùng.

## 8. Ví dụ hoàn chỉnh: thứ tự và parallel Stream

Tệp StreamOrderDemo.java:

~~~java
import java.util.ArrayList;
import java.util.List;

public class StreamOrderDemo {
    public static void main(String[] args) {
        List<Integer> source = List.of(1, 2, 3, 4, 5, 6);

        List<Integer> mapped = source.parallelStream()
                .map(value -> value * 10)
                .toList();

        List<Integer> orderedActions = new ArrayList<>();
        source.parallelStream()
                .forEachOrdered(orderedActions::add);

        int first = source.parallelStream()
                .findFirst()
                .orElseThrow();

        int any = source.parallelStream()
                .findAny()
                .orElseThrow();

        List<Integer> prefix = source.parallelStream()
                .takeWhile(value -> value < 4)
                .toList();

        List<Integer> remainder = source.parallelStream()
                .dropWhile(value -> value < 4)
                .toList();

        long unorderedLimitCount = source.parallelStream()
                .unordered()
                .limit(3)
                .count();

        System.out.println("parallel toList: " + mapped);
        System.out.println("forEachOrdered: " + orderedActions);
        System.out.println("findFirst: " + first);
        System.out.println("findAny is a source member: " + source.contains(any));
        System.out.println("takeWhile: " + prefix);
        System.out.println("dropWhile: " + remainder);
        System.out.println("unordered limit count: " + unorderedLimitCount);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 StreamOrderDemo.java
java StreamOrderDemo
~~~

Kết quả chuẩn:

~~~text
parallel toList: [10, 20, 30, 40, 50, 60]
forEachOrdered: [1, 2, 3, 4, 5, 6]
findFirst: 1
findAny is a source member: true
takeWhile: [1, 2, 3]
dropWhile: [4, 5, 6]
unordered limit count: 3
~~~

Dòng kiểm tra findAny chỉ xác nhận giá trị trả về thuộc nguồn. Giá trị cụ thể có thể là bất kỳ phần tử nào trong nguồn. Ví dụ không in trực tiếp giá trị đó để tránh tạo ấn tượng sai rằng findAny luôn trả về phần tử đầu tiên.

Ví dụ dùng parallel Stream nhưng vẫn có kết quả ổn định ở những thao tác có cam kết encounter order. unordered().limit(3) chỉ bảo đảm số lượng phần tử được đếm là 3, không bảo đảm ba phần tử cụ thể nào được chọn.

## 9. Chọn thao tác theo yêu cầu

| Yêu cầu | Thao tác phù hợp |
|---|---|
| Duyệt và xử lý mọi phần tử, không cần thứ tự | forEach |
| Thực hiện hành động theo encounter order | forEachOrdered |
| Lấy đúng phần tử đầu tiên | findFirst |
| Lấy một phần tử phù hợp bất kỳ | findAny |
| Giữ n phần tử đầu theo thứ tự nguồn | limit |
| Bỏ n phần tử đầu theo thứ tự nguồn | skip |
| Giữ tiền tố thỏa điều kiện | takeWhile |
| Bỏ tiền tố thỏa điều kiện | dropWhile |
| Bỏ ràng buộc encounter order khi nghiệp vụ cho phép | unordered |
| Tạo List giữ thứ tự của ordered Stream | toList |

## 10. Checklist khi review parallel Stream

- Xác định nguồn có encounter order hay không.
- Phân biệt thứ tự xử lý trên thread với thứ tự kết quả.
- Dùng forEachOrdered khi hành động cuối cần đúng thứ tự.
- Dùng findFirst khi cần phần tử đầu tiên; dùng findAny khi bất kỳ phần tử phù hợp nào cũng được.
- Chỉ dùng unordered() nếu nghiệp vụ không phụ thuộc vào thứ tự.
- Kiểm tra limit, skip, takeWhile và dropWhile vì chúng có thể cần phối hợp để giữ thứ tự.
- Tránh sửa trạng thái dùng chung trong map, filter hoặc forEach song song.
- Ưu tiên reduce và collector để tổng hợp dữ liệu.
- Không giả định parallel Stream luôn nhanh hơn sequential Stream.
- Đo hiệu năng bằng dữ liệu đại diện và kiểm thử cả tính đúng đắn lẫn độ an toàn luồng.

Thứ tự duyệt là một phần của ngữ nghĩa Stream khi nguồn có encounter order. Chế độ song song chỉ thay đổi cách công việc được thực hiện; nó không tự xóa các cam kết về kết quả. Khi xác định rõ yêu cầu về thứ tự, trạng thái và side effects, có thể chọn thao tác Stream phù hợp mà vẫn tận dụng được parallel processing khi có lợi.