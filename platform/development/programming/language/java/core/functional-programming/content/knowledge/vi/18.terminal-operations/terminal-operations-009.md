# Thao tác ngắn mạch và phần tử có thể không được xử lý trong Java Stream

## 1. Mục tiêu bài học

Khi lập trình với Java Stream, nhiều người hình dung rằng mọi phần tử trong nguồn sẽ lần lượt đi qua tất cả các lambda của **map**, **filter**, **peek** rồi mới có kết quả. Hình dung đó **không phải là cam kết của Stream API**. Một số thao tác có thể kết thúc việc đánh giá ngay khi đủ thông tin, gọi là **short-circuiting operations** (thao tác ngắn mạch). Ngoài ra, Stream có thể tối ưu để bỏ qua những bước không cần thiết cho kết quả cuối.

Ví dụ: để trả lời “Có số nào lớn hơn 100 không?”, chỉ cần thấy một số thỏa điều kiện là đủ. Không cần tiếp tục kiểm tra toàn bộ nguồn. Vì thế, đặt hành động bắt buộc như “ghi nhận đã xử lý mọi phần tử” trong lambda của **filter** hoặc **map** có thể dẫn tới sai nghiệp vụ.

Sau bài học, bạn có thể:

- Phân biệt **short-circuiting terminal operation** với **short-circuiting intermediate operation**.
- Hiểu **anyMatch**, **allMatch**, **noneMatch**, **findFirst**, **findAny**, **limit**, **takeWhile** và phân biệt với **dropWhile**.
- Dự đoán đúng kết quả boolean/Optional và giải thích vì sao một số phần tử **có thể không được duyệt hoặc một số callback không được gọi**.
- Hiểu tính **lazy** của Stream, encounter order, parallel execution, và ảnh hưởng của các bước **sorted**, **distinct**.
- Tránh dựa vào side effect của **peek/map/filter** làm bằng chứng xử lý đủ phần tử.
- Thiết kế và kiểm thử pipeline có ý nghĩa nghiệp vụ đúng, với ví dụ chạy trên **Java 17**.

## 2. Bối cảnh: Stream chỉ đánh giá khi cần

Một pipeline gồm:

~~~java
Stream<Integer> pipeline = List.of(1, 2, 3, 4, 5).stream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * 10);
~~~

Đây là mã minh họa, cần import **List** và **Stream**, đặt trong một phương thức. Sau khi tạo biến **pipeline**, **chưa có terminal operation**, nên việc dựng pipeline không yêu cầu duyệt List và tính tất cả kết quả.

Khi gọi:

~~~java
List<Integer> result = pipeline.toList();
System.out.println(result); // [20, 40]
~~~

**toList()** kích hoạt đánh giá để tạo danh sách kết quả. Các thao tác trung gian **filter** và **map** là **lazy**: chúng mô tả cách xử lý thay vì tính trước toàn bộ một tập kết quả trung gian.

Một terminal khác có thể cần ít dữ liệu hơn:

~~~java
boolean hasEven = List.of(1, 3, 4, 6).stream()
        .anyMatch(n -> n % 2 == 0); // true
~~~

Trong cách chạy tuần tự thông thường, khi gặp 4 thì đã có thể xác định **true**, nên 6 không cần được kiểm tra. Đây là trường hợp short-circuit dễ hiểu.

**Điểm quan trọng:** Stream API bảo đảm **ngữ nghĩa của kết quả**, không bảo đảm mọi callback chạy đúng một số lần hoặc theo một trace cố định trong mọi implementation, terminal, source và mode (sequential/parallel).

## 3. Thao tác ngắn mạch là gì?

Một thao tác **short-circuiting** có thể đưa ra kết quả hữu hạn **mà không cần tiêu thụ toàn bộ nguồn**, nếu có đủ thông tin để kết luận.

Có hai nhóm đáng chú ý:

| Nhóm | Thao tác | Khả năng dừng sớm |
| --- | --- | --- |
| **Terminal** | **anyMatch(predicate)** | Dừng khi tìm thấy một phần tử thỏa điều kiện |
| **Terminal** | **allMatch(predicate)** | Dừng khi gặp một phần tử không thỏa |
| **Terminal** | **noneMatch(predicate)** | Dừng khi gặp một phần tử thỏa |
| **Terminal** | **findFirst()** | Có thể dừng khi xác định phần tử đầu theo encounter order |
| **Terminal** | **findAny()** | Có thể dừng khi tìm thấy phần tử bất kỳ |
| **Intermediate** | **limit(n)** | Không cần xuất quá n phần tử cho bước phía sau |
| **Intermediate** | **takeWhile(predicate)** | Với ordered stream, dừng lấy phần tử khi gặp phần tử đầu tiên không thỏa |

Những thao tác như **filter**, **map** và **peek** là intermediate lazy, nhưng **không được gọi là short-circuiting chỉ vì chúng lazy**. Bản thân chúng không nhất thiết quyết định “đã đủ kết quả”. Việc toàn pipeline dừng hay tiếp tục phụ thuộc các thao tác phía sau.

**dropWhile(predicate)** cũng cần được học cùng **takeWhile**, nhưng nó **không giống takeWhile về tính ngắn mạch**: dropWhile bỏ tiền tố ban đầu thỏa điều kiện, rồi chuyển tiếp những phần tử còn lại. Nó không có nghĩa bỏ hẳn mọi dữ liệu sau một lần gặp phần tử không thỏa.

## 4. anyMatch: chỉ cần một phần tử đúng

Chữ ký:

~~~java
boolean anyMatch(Predicate<? super T> predicate)
~~~

Ý nghĩa: có **ít nhất một** phần tử thỏa predicate hay không?

~~~java
boolean found = List.of(3, 5, 8, 10).stream()
        .anyMatch(n -> n % 2 == 0);

System.out.println(found); // true
~~~

Với một sequential ordered stream đơn giản, Java có thể dừng sau khi thấy 8; không nhất thiết kiểm tra 10.

Các trường hợp:

- Có ít nhất một phần tử thỏa → **true**.
- Có phần tử nhưng không phần tử nào thỏa → **false**.
- Stream rỗng → **false**.

Đối với nghiệp vụ, **anyMatch** phù hợp với câu hỏi “Có bất kỳ đơn hàng nào vượt hạn mức?”, “Có quyền nào cho phép thao tác này?” hoặc “Có bản ghi nào cần xử lý không?”.

### 4.1. Đừng hiểu kết quả true là “đã kiểm tra mọi phần tử”

~~~java
boolean hasExpired = orders.stream()
        .anyMatch(Order::expired);
~~~

Đoạn này giả định lớp Order có phương thức **expired()**. Nếu một đơn hết hạn xuất hiện sớm, các đơn phía sau có thể không được gọi **expired()**.

Nếu hệ thống phải tạo báo cáo **cho từng đơn**, không được dùng số lượt gọi callback trong anyMatch để chứng minh đã đánh giá toàn bộ.

## 5. allMatch: chỉ cần một phần tử sai

Chữ ký:

~~~java
boolean allMatch(Predicate<? super T> predicate)
~~~

Ý nghĩa: **mọi phần tử** của stream có thỏa predicate không?

~~~java
boolean allPositive = List.of(2, 3, -1, 8).stream()
        .allMatch(n -> n > 0);
System.out.println(allPositive); // false
~~~

Trong pipeline tuần tự đơn giản, khi gặp -1 đã biết không phải mọi phần tử đều dương, nên 8 không cần được kiểm tra.

Các trường hợp:

- Tất cả phần tử đều true → **true**.
- Chỉ một phần tử false → **false**, có thể dừng sớm.
- Stream rỗng → **true**.

### 5.1. Vì sao allMatch trên stream rỗng là true?

Theo logic toán học, mệnh đề “**mọi phần tử** trong tập rỗng thỏa P” là **đúng theo chân trị rỗng (vacuous truth)**, vì không có phản ví dụ. Điều này thường bất ngờ với người mới:

~~~java
boolean ready = Stream.<String>empty()
        .allMatch(s -> !s.isBlank());
System.out.println(ready); // true
~~~

**Không có phần tử** không nhất thiết tương đương **tất cả phần tử sẵn sàng** theo ý nghĩa nghiệp vụ. Nếu yêu cầu “có ít nhất một mục và tất cả đều hợp lệ”, cần kiểm tra **không rỗng** riêng hoặc dùng một phép tổng hợp kết quả đủ hai thông tin. Không được lấy `allMatch` trên tập rỗng làm bằng chứng đã duyệt bản ghi nào.

## 6. noneMatch: chỉ cần một phần tử đúng để phủ định

Chữ ký:

~~~java
boolean noneMatch(Predicate<? super T> predicate)
~~~

Ý nghĩa: **không có bất kỳ** phần tử nào thỏa điều kiện?

~~~java
boolean noNegative = List.of(1, 2, 3).stream()
        .noneMatch(n -> n < 0);
System.out.println(noNegative); // true
~~~

Nếu một số âm xuất hiện, **noneMatch** có thể dừng ngay với false.

Trường hợp stream rỗng: **noneMatch trả true**, vì thật sự không có phần tử nào vi phạm điều kiện.

### 6.1. So sánh ba phép match

Giả sử predicate là `n -> n % 2 == 0`:

| Nguồn | anyMatch | allMatch | noneMatch |
| --- | --- | --- | --- |
| `[2,4,6]` | true | true | false |
| `[1,2,3]` | true | false | false |
| `[1,3,5]` | false | false | true |
| `[]` | **false** | **true** | **true** |

Các kết quả trên là **logic boolean của tập phần tử**. Việc có bao nhiêu lời gọi predicate là vấn đề thực thi khác, không được suy ra chỉ từ bảng.

## 7. findFirst và findAny: trả một Optional

### 7.1. findFirst

~~~java
Optional<Integer> first = List.of(1, 3, 4, 6).stream()
        .filter(n -> n % 2 == 0)
        .findFirst();

System.out.println(first.orElse(-1)); // 4
~~~

**findFirst()** là terminal short-circuiting, trả **Optional<T>**:

- Nếu tìm được, trả phần tử **đầu theo encounter order** nếu stream có thứ tự.
- Nếu không có, trả **Optional.empty()**.
- Nếu phần tử được chọn là null, **findFirst có thể ném NullPointerException**, bởi Optional không chứa được null.

Trên **List stream** có encounter order, filter giữ thứ tự tương đối, nên kết quả ví dụ là số chẵn đầu tiên: 4.

### 7.2. findAny

~~~java
Optional<Integer> any = List.of(2, 4, 6).stream()
        .filter(n -> n > 0)
        .findAny();

System.out.println(any.isPresent()); // true
~~~

**findAny()** được thiết kế để có thể trả **bất kỳ phần tử phù hợp**. Đặc biệt với parallel stream, không nên kỳ vọng giá trị cụ thể là 2, 4 hay 6 chỉ vì nguồn có thứ tự.

**Quy tắc chọn:** nếu nghiệp vụ cần **phần tử đầu tiên** theo thứ tự, chọn **findFirst**. Nếu chỉ cần **một phần tử bất kỳ** và không cần vị trí, chọn **findAny**. Không viết test đòi findAny của parallel stream luôn trả phần tử đầu.

### 7.3. Không đồng nhất empty với lỗi

`Optional.empty()` từ findFirst/findAny nghĩa là không tìm được phần tử trong stream được đánh giá. Nó **không phải** bằng chứng một database hay API ngoài đã hoạt động thành công nếu quá trình tìm kiếm thực tế gặp exception. Khi có lỗi hệ thống, cần để lỗi được phản hồi theo hợp đồng, không âm thầm biến thành “không tìm thấy”.

## 8. limit: short-circuiting intermediate

`limit(long maxSize)` là **stateful short-circuiting intermediate operation**. Nó chỉ để tối đa **maxSize** phần tử đi qua bước này.

~~~java
List<Integer> firstThree = List.of(10, 20, 30, 40, 50)
        .stream()
        .limit(3)
        .toList();

System.out.println(firstThree); // [10, 20, 30]
~~~

Với ordered sequential stream đơn giản, terminal có thể lấy đủ ba phần tử rồi dừng, không cần xem phần còn lại.

Lưu ý:

- `limit(0)` cho kết quả rỗng.
- `limit(n)` cần n **không âm**; `limit(-1)` ném `IllegalArgumentException`.
- Với nguồn có encounter order, **limit** phải giữ đúng tiền tố n phần tử.
- Với unordered stream, tập n phần tử được lấy có thể khác nhau, nhưng kết quả vẫn chứa tối đa n phần tử.

### 8.1. filter rồi limit khác limit rồi filter

~~~java
List<Integer> a = List.of(1, 2, 3, 4, 5, 6).stream()
        .filter(n -> n % 2 == 0)
        .limit(2)
        .toList();

List<Integer> b = List.of(1, 2, 3, 4, 5, 6).stream()
        .limit(2)
        .filter(n -> n % 2 == 0)
        .toList();
~~~

Kết quả:

- **a = [2, 4]**: chọn **hai số chẵn đầu tiên**.
- **b = [2]**: chỉ xem **hai phần tử đầu nguồn**, sau đó giữ số chẵn.

Không được đổi vị trí limit và filter chỉ với lý do “cả hai đều là intermediate operation”: thứ tự là một phần của ngữ nghĩa.

### 8.2. Limit trên stream vô hạn

~~~java
List<Integer> firstFive = Stream.iterate(1, n -> n + 1)
        .limit(5)
        .toList();

System.out.println(firstFive); // [1, 2, 3, 4, 5]
~~~

Nguồn `Stream.iterate(1, n -> n + 1)` có thể cung cấp vô hạn phần tử. `limit(5)` làm kết quả hữu hạn, nên terminal có thể hoàn tất trong tình huống này.

Tuy nhiên, khi ghép với thao tác stateful như **sorted()** trước limit, việc sắp toàn bộ một nguồn vô hạn nói chung không thể cho ra phần tử đầu một cách hữu hạn; cần thiết kế thứ tự pipeline cẩn thận.

## 9. takeWhile và dropWhile trong Java 9+

Hai thao tác này được đưa vào Stream từ Java 9. Chúng có ý nghĩa đặc biệt khi nguồn **có encounter order**.

### 9.1. takeWhile: lấy tiền tố còn thỏa điều kiện

~~~java
List<Integer> prefix = List.of(1, 2, 3, 1, 0).stream()
        .takeWhile(n -> n < 3)
        .toList();

System.out.println(prefix); // [1, 2]
~~~

Với ordered stream, **takeWhile** lấy **tiền tố dài nhất** mà mọi phần tử đều thỏa điều kiện. Khi gặp 3 (không thỏa n < 3), nó **dừng lấy**: hai phần tử 1 và 0 phía sau **không được lấy**, dù chúng thỏa predicate.

So với filter:

~~~java
List<Integer> filtered = List.of(1, 2, 3, 1, 0).stream()
        .filter(n -> n < 3)
        .toList();

System.out.println(filtered); // [1, 2, 1, 0]
~~~

**filter** chọn mọi phần tử thỏa trong toàn bộ nguồn được đánh giá; **takeWhile** chọn một **tiền tố liên tục** và có thể dừng sớm.

### 9.2. dropWhile: bỏ tiền tố rồi giữ phần còn lại

~~~java
List<Integer> rest = List.of(1, 2, 3, 1, 0).stream()
        .dropWhile(n -> n < 3)
        .toList();

System.out.println(rest); // [3, 1, 0]
~~~

Với ordered stream, **dropWhile** bỏ tiền tố đầu thỏa predicate (**1,2**). Khi gặp 3, nó ngừng bỏ và chuyển tiếp **tất cả phần còn lại**, kể cả 1 và 0 tuy thỏa predicate.

Không được hiểu dropWhile như “loại mọi phần tử thỏa” — đó là filter với predicate phủ định.

**Đặc tính ngữ nghĩa:** `takeWhile` là short-circuiting stateful intermediate operation. `dropWhile` là stateful intermediate operation nhưng không có nghĩa dừng xử lý toàn bộ nguồn khi kết thúc vùng bỏ.

### 9.3. Với unordered stream

Khi không có encounter order, khái niệm “tiền tố đầu tiên” không còn xác định như ở List. Hợp đồng **takeWhile/dropWhile** cho phép lựa chọn một **tập con phù hợp** theo điều kiện được quy định cho unordered stream, không bảo đảm một tiền tố theo thứ tự hiển thị của bạn.

Nếu nghiệp vụ dựa trên “từ đầu danh sách đến sự kiện dừng”, hãy dùng **nguồn có thứ tự** và giữ ordered semantics. Cũng cần thận trọng với parallel stream: việc duy trì ranh giới tiền tố trên ordered stream có thể tốn chi phí.

## 10. Thứ tự pipeline thay đổi khả năng dừng sớm

### 10.1. sorted trước findFirst

~~~java
int smallest = List.of(9, 2, 5).stream()
        .sorted()
        .findFirst()
        .orElseThrow();

System.out.println(smallest); // 2
~~~

Mặc dù findFirst có thể dừng sau khi nhận được **phần tử đầu của Stream đã sắp**, bước **sorted** là **stateful** và thường phải nhận toàn bộ đầu vào hữu hạn để xác định thứ tự. Vì vậy, không thể kết luận “findFirst luôn chỉ xem một phần tử của nguồn gốc”.

Nếu chỉ cần tìm min, viết trực tiếp:

~~~java
int minimum = List.of(9, 2, 5).stream()
        .min(Integer::compareTo)
        .orElseThrow();
~~~

**min** là phép tổng hợp cực trị; thông thường cần xét các phần tử để biết phần tử nhỏ nhất, nhưng không cần tạo một chuỗi đã sắp chỉ để lấy phần tử đầu. Cả hai cho giá trị 2 trong ví dụ. Trên Stream<Integer>, `min(Comparator)` trả Optional<Integer>.

### 10.2. sorted rồi limit khác limit rồi sorted

~~~java
List<Integer> bestTwo = List.of(7, 1, 9, 3).stream()
        .sorted()
        .limit(2)
        .toList();

List<Integer> sortedPrefix = List.of(7, 1, 9, 3).stream()
        .limit(2)
        .sorted()
        .toList();
~~~

Kết quả lần lượt **[1,3]** và **[1,7]**. Cách đầu là “chọn hai số nhỏ nhất toàn bộ”; cách thứ hai chỉ sắp hai phần tử xuất hiện đầu tiên. Short-circuit không có nghĩa bạn được tự ý đổi thứ tự thao tác mà giữ nguyên ý nghĩa.

### 10.3. distinct và stateful pipeline

`distinct()` là stateful intermediate operation: nó có thể phải ghi nhớ phần tử đã gặp để loại trùng. Trên ordered stream, nó giữ phần tử xuất hiện trước trong mỗi nhóm bằng nhau; trên unordered stream, lựa chọn đại diện có thể khác. Khi ghép `distinct().limit(k)`, số lượng nguồn cần duyệt để tạo k giá trị khác nhau có thể lớn hơn k.

Ví dụ:

~~~java
List<Integer> uniqueTwo = List.of(1, 1, 2, 2, 3)
        .stream()
        .distinct()
        .limit(2)
        .toList();

System.out.println(uniqueTwo); // [1, 2]
~~~

Không nên suy luận limit(2) khiến chỉ hai phần tử **gốc** được kiểm tra; để lấy đủ hai giá trị khác nhau, pipeline có thể cần xem thêm phần tử.

## 11. Vì sao một số callback có thể không được gọi?

Có **hai nguyên nhân lớn**:

1. **Short-circuit:** một terminal hoặc intermediate operation đã đủ thông tin để kết thúc/giới hạn việc duyệt.
2. **Tối ưu của Stream:** implementation có thể tính kết quả mà không cần gọi một số behavioral parameter nếu việc bỏ qua chúng không ảnh hưởng kết quả terminal.

Ví dụ quan trọng:

~~~java
long size = List.of("A", "B", "C").stream()
        .peek(System.out::println)
        .count();

System.out.println(size); // 3
~~~

**Không được khẳng định** rằng A, B và C chắc chắn được in. Nếu nguồn có kích thước đã biết và pipeline không thay đổi số phần tử, **count() có thể xác định size mà không duyệt**, khiến `peek` không được gọi.

Tương tự:

~~~java
long count = List.of(1, 2, 3, 4).stream()
        .map(n -> n * 100)
        .count();
~~~

Kết quả count là 4; việc tính n * 100 có thể không cần thiết. Nếu bạn đặt hành động ghi dữ liệu bắt buộc bên trong map, hành động đó không được bảo đảm thực hiện khi terminal chỉ cần số phần tử.

**Không dùng peek, map, filter, comparator hoặc predicate để thay thế một bước audit/ghi giao dịch bắt buộc.** Chúng là những phần của mô tả pipeline và có thể bị gọi ít lần, nhiều lần hoặc theo thứ tự khác trong giới hạn đặc tả.

### 11.1. Lazy không phải chạy nền

Một pipeline chưa có terminal **chưa bắt đầu tính kết quả**, nhưng không phải vì nó đã được lên lịch chạy ở thread nền. Lazy khác asynchronous. Với một sequential stream, terminal operation chạy trên luồng gọi nó theo cơ chế thông thường. Khi dùng parallel, Stream có thể xử lý các phần khác nhau trên nhiều thread.

### 11.2. Cơ chế dừng sớm không phải lời hứa về số callback

Đặc biệt với parallel stream, nhiều tác vụ có thể được khởi động trước khi có kết quả đủ để quyết định dừng, nên một số callback “không cần cho kết quả cuối” vẫn có thể được gọi. Short-circuit nghĩa là **có thể không cần tiêu thụ hết nguồn**, không có nghĩa các tác vụ khác đều dừng tức thì ngay sau callback đầu tiên tìm ra đáp án.

## 12. Ví dụ Java 17 hoàn chỉnh

Chương trình dưới đây dùng **sequential stream** để minh họa các điểm có thể quan sát: dừng sớm khi đã có đáp án, khác biệt giữa filter và takeWhile/dropWhile, và khi bước sorted khiến nhiều đầu vào phải được kiểm tra.

Tạo tệp **ShortCircuitStreamDemo.java**:

~~~java
import java.util.List;
import java.util.OptionalInt;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class ShortCircuitStreamDemo {
    public static void main(String[] args) {
        AtomicInteger anyChecks = new AtomicInteger();
        boolean anyGreaterThanThree = IntStream.rangeClosed(1, 8)
                .anyMatch(n -> {
                    anyChecks.incrementAndGet();
                    return n > 3;
                });

        System.out.println("any > 3: " + anyGreaterThanThree);
        System.out.println("any checks: " + anyChecks.get());

        AtomicInteger allChecks = new AtomicInteger();
        boolean allEven = IntStream.of(2, 4, 5, 6)
                .allMatch(n -> {
                    allChecks.incrementAndGet();
                    return n % 2 == 0;
                });

        System.out.println("all even: " + allEven);
        System.out.println("all checks: " + allChecks.get());

        boolean noneEven = IntStream.of(1, 3, 5)
                .noneMatch(n -> n % 2 == 0);
        System.out.println("none even: " + noneEven);

        boolean emptyAny = IntStream.empty().anyMatch(n -> n > 0);
        boolean emptyAll = IntStream.empty().allMatch(n -> n > 0);
        boolean emptyNone = IntStream.empty().noneMatch(n -> n > 0);
        System.out.println("empty match: "
                + emptyAny + "/" + emptyAll + "/" + emptyNone);

        AtomicInteger findChecks = new AtomicInteger();
        OptionalInt firstMultipleOfThree = IntStream.rangeClosed(1, 8)
                .filter(n -> {
                    findChecks.incrementAndGet();
                    return n % 3 == 0;
                })
                .findFirst();

        System.out.println("first multiple of 3: "
                + firstMultipleOfThree.orElse(-1));
        System.out.println("find checks: " + findChecks.get());

        AtomicInteger limitChecks = new AtomicInteger();
        List<Integer> twoEven = IntStream.rangeClosed(1, 8)
                .filter(n -> {
                    limitChecks.incrementAndGet();
                    return n % 2 == 0;
                })
                .limit(2)
                .boxed()
                .toList();

        System.out.println("first two even: " + twoEven);
        System.out.println("limit checks: " + limitChecks.get());

        List<Integer> input = List.of(1, 2, 3, 1, 0);
        System.out.println("takeWhile: " + input.stream()
                .takeWhile(n -> n < 3)
                .toList());
        System.out.println("dropWhile: " + input.stream()
                .dropWhile(n -> n < 3)
                .toList());
        System.out.println("filter: " + input.stream()
                .filter(n -> n < 3)
                .toList());

        AtomicInteger sortedInput = new AtomicInteger();
        int smallest = Stream.of(9, 2, 5, 7)
                .map(n -> {
                    sortedInput.incrementAndGet();
                    return n;
                })
                .sorted()
                .findFirst()
                .orElseThrow();

        System.out.println("sorted first: " + smallest);
        System.out.println("sorted input: " + sortedInput.get());

        boolean findAnyPresent = Stream.of("A", "B", "C")
                .findAny()
                .isPresent();
        System.out.println("findAny present: " + findAnyPresent);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac ShortCircuitStreamDemo.java
java ShortCircuitStreamDemo
~~~

**Kết quả chương trình tuần tự này:**

~~~text
any > 3: true
any checks: 4
all even: false
all checks: 3
none even: true
empty match: false/true/true
first multiple of 3: 3
find checks: 3
first two even: [2, 4]
limit checks: 4
takeWhile: [1, 2]
dropWhile: [3, 1, 0]
filter: [1, 2, 1, 0]
sorted first: 2
sorted input: 4
findAny present: true
~~~

### 12.1. Vì sao any checks bằng 4?

IntStream.rangeClosed(1,8) tạo dãy có thứ tự **1,2,...,8**. Predicate `n > 3` sai với 1,2,3 và đúng tại 4. Trong pipeline tuần tự này, **anyMatch** dừng khi đã biết kết quả true, nên bộ đếm quan sát là 4.

Đây là kết quả cụ thể của chương trình, **không phải yêu cầu mọi implementation/parallel pipeline phải gọi predicate đúng bốn lần** với mọi biến thể của code.

### 12.2. Vì sao all checks bằng 3?

Dãy **2,4,5,6** có hai phần tử đầu chẵn, phần tử thứ ba (5) lẻ. Từ 5, **allMatch** đã biết kết quả false và không cần kiểm tra 6 trong cách thực thi tuần tự này.

### 12.3. Vì sao empty match là false/true/true?

- **anyMatch trên rỗng:** không có phần tử thỏa → false.
- **allMatch trên rỗng:** không có phản ví dụ → true.
- **noneMatch trên rỗng:** không có phần tử vi phạm điều “không phần tử nào thỏa” → true.

Ba kết quả này là hợp đồng API, không phụ thuộc vào chuyện có callback được gọi hay không (trong stream rỗng không có phần tử để kiểm tra).

### 12.4. Vì sao first two even có limit checks = 4?

Pipeline **filter(n%2==0).limit(2)** cần tìm **hai số chẵn đầu tiên**: 2 và 4. Với nguồn tuần tự 1,2,3,4, bước filter kiểm tra bốn số rồi limit đã đủ hai giá trị. Đổi thành **limit(2).filter(...)** thì kết quả chỉ là [2].

### 12.5. Vì sao sorted input bằng 4?

Đầu vào của sort là 9,2,5,7. Để phát ra phần tử nhỏ nhất theo thứ tự sắp xếp, thao tác **sorted** đã lấy cả bốn số trong chương trình này. **findFirst** có thể dừng ở phần tử đầu **sau sorted**, nhưng không suy ra nguồn gốc chỉ được duyệt một phần tử.

### 12.6. Vì sao không in giá trị của findAny?

`findAny()` chỉ bảo đảm một phần tử phù hợp nếu có; **không bảo đảm đó là phần tử đầu trong mọi mode**. Vì vậy ví dụ in **isPresent()** để kiểm tra hợp đồng mà không đưa ra kỳ vọng sai về phần tử được chọn.

### 12.7. Bộ đếm chỉ là công cụ học tập

Các AtomicInteger ở ví dụ có tác dụng phụ và chỉ dùng để nhìn cách thực thi của pipeline tuần tự. Chúng **không đại diện cho một hệ thống audit đúng**. Trong code production, kết quả nghiệp vụ phải được xác định bằng semantics của terminal, còn việc ghi audit phải được thiết kế riêng.

## 13. Parallel stream: ngắn mạch không bảo đảm dừng tức thì

Nếu chạy:

~~~java
boolean anyMatch = numbers.parallelStream()
        .anyMatch(n -> expensiveCheck(n));
~~~

Đây là mảnh ghép có List `numbers` và hàm `expensiveCheck` đã định nghĩa. Dù một thread tìm được kết quả true sớm, một số thread khác **có thể đã chạy hoặc vẫn hoàn tất phần việc đang xử lý**.

Những điều cần nhớ:

- **anyMatch/findAny** có thể đạt kết quả mà không cần giữ encounter order.
- **findFirst** phải quan tâm encounter order khi nguồn ordered; việc xác định phần tử đầu có thể tốn thêm công việc so với findAny.
- **limit(n)** trên ordered parallel stream phải bảo đảm lấy đúng tiền tố n phần tử; có thể tốn tài nguyên hơn unordered.
- **takeWhile/dropWhile** trên ordered parallel stream cần bảo đảm ranh giới tiền tố, đôi khi gây chi phí đáng kể.
- Thứ tự callback chạy không cố định, kể cả khi kết quả cuối có order theo hợp đồng.
- Cancellation của short-circuit là **cơ chế phối hợp có thể dừng sớm**, không phải cam kết “không callback nào chạy sau khi một thread đã xác định đáp án”.

### 13.1. Không cập nhật shared mutable state từ callback

~~~java
// Không nên làm như một bước nghiệp vụ bắt buộc:
AtomicInteger checked = new AtomicInteger();

boolean found = numbers.parallelStream()
        .anyMatch(n -> {
            checked.incrementAndGet();
            return n > 100;
        });
~~~

AtomicInteger tăng nguyên tử, nhưng **checked không đại diện cho số phần tử bắt buộc được xử lý**. Các lần kiểm tra có thể ít hơn kích thước nguồn, phụ thuộc cách chia việc và thời điểm dừng. Một mutable counter không làm cho predicate trở nên stateless.

Nếu muốn đo số callback cho một bài benchmark, cần phân biệt rõ số callback thực thi, số phần tử nguồn và thời gian hoàn thành; không lấy bộ đếm callback làm hợp đồng xử lý dữ liệu.

## 14. Thiết kế Predicate an toàn cho thao tác ngắn mạch

Những predicate dùng với Stream nên **non-interfering** và **stateless**:

- **Non-interfering:** không sửa nguồn đang duyệt.
- **Stateless:** không phụ thuộc vào trạng thái bị thay đổi giữa các lời gọi callback.
- **Có kết quả rõ ràng:** cùng một phần tử và cùng cấu hình ổn định nên cho cùng quyết định.
- **Không giấu hiệu ứng bắt buộc:** nếu callback không được gọi, nghiệp vụ không bị mất bước thiết yếu.

Ví dụ **phù hợp**:

~~~java
int minimumAmount = 100;
Predicate<Order> expensive =
        order -> order.totalAmount() >= minimumAmount;
~~~

Đây là mảnh ghép với kiểu Order có method totalAmount(). Biến **minimumAmount** được capture và effectively final, nên điều kiện ổn định trong phạm vi này.

Ví dụ **không phù hợp**:

~~~java
int[] inspected = {0};
Predicate<Order> everyThirdCall = order ->
        (++inspected[0]) % 3 == 0;
~~~

Cách này thay đổi kết quả tùy **số lượt callback**, không tùy dữ liệu Order. Short-circuit, parallel và tối ưu có thể thay đổi danh sách được chọn. Việc biến cục bộ `inspected` chứa tham chiếu mảng vẫn effectively final **không làm nội dung mảng bất biến**.

Nếu nghiệp vụ thật sự cần chọn “mỗi phần tử thứ ba” theo vị trí, hãy biểu diễn vị trí qua một chỉ số rõ ràng từ nguồn có thứ tự, thay vì dùng số lần Predicate được gọi.

## 15. Trường hợp kinh doanh: chọn đúng terminal

Giả sử có danh sách đơn hàng:

| Câu hỏi nghiệp vụ | Công cụ phù hợp |
| --- | --- |
| Có đơn nào quá hạn? | **anyMatch(Order::isOverdue)** |
| Tất cả đơn có hợp lệ? | **allMatch(Order::isValid)**, nhưng phải xử lý trường hợp danh sách rỗng nếu yêu cầu ít nhất một đơn |
| Không đơn nào bị khóa? | **noneMatch(Order::isLocked)** |
| Lấy đơn hợp lệ đầu tiên theo thứ tự ưu tiên? | **filter(...).findFirst()**, với stream đã có đúng encounter order |
| Chỉ cần một đơn hợp lệ bất kỳ? | **filter(...).findAny()** |
| Lấy 20 đơn đầu sau lọc? | **filter(...).limit(20).toList()** |
| Lấy các sự kiện liên tục cho tới lần đầu gặp tín hiệu STOP? | **takeWhile(event -> !event.isStop())**, trên ordered stream |
| Bỏ phần tiêu đề/sự kiện khởi động đầu log, giữ phần còn lại? | **dropWhile(event -> event.isHeader())**, trên ordered stream |

Quan trọng: nếu thứ tự “đầu tiên” là nghiệp vụ (theo thời gian, độ ưu tiên, ID), phải bảo đảm **dữ liệu đầu vào được sắp đúng thứ tự**. `findFirst` trên một stream không có encounter order không tự tạo ý nghĩa “mới nhất” hay “quan trọng nhất”.

Nếu muốn chọn đơn mới nhất, có thể dùng **max(comparator)** thay vì sắp toàn bộ rồi findFirst, nhưng vẫn phải xét dữ liệu đủ để xác định cực trị. Short-circuit không tự thay thế yêu cầu xét mọi phần tử khi phải tìm min/max toàn cục.

## 16. Kiểm thử đúng điều gì?

### 16.1. Kiểm thử kết quả boolean và phần tử

Kiểm tra các tình huống:

1. **anyMatch**: không có phần tử phù hợp, có phần tử phù hợp, source rỗng.
2. **allMatch**: mọi phần tử đúng, chỉ một phần tử sai, source rỗng.
3. **noneMatch**: không phần tử đúng, có phần tử đúng, source rỗng.
4. **findFirst**: đúng phần tử đầu với nguồn ordered, hoặc Optional.empty nếu không có.
5. **findAny**: kiểm tra kết quả thuộc tập các phần tử phù hợp, **không áp đặt giá trị cố định** trong parallel.
6. **limit**: đúng tiền tố khi nguồn ordered; `limit(0)` rỗng, limit âm bị từ chối.
7. **takeWhile/dropWhile**: đúng ranh giới tiền tố ngay tại phần tử đầu tiên không thỏa.
8. **sorted + findFirst**: trả kết quả so sánh đúng, không nhầm số phần tử nguồn cần tiêu thụ.

### 16.2. Không ràng buộc số lần callback nếu API không bảo đảm

Một test như:

~~~java
AtomicInteger counter = new AtomicInteger();

boolean exists = IntStream.rangeClosed(1, 100)
        .anyMatch(n -> {
            counter.incrementAndGet();
            return n == 2;
        });

if (!exists) {
    throw new AssertionError("Expected a match");
}
~~~

Có thể dùng counter để **quan sát trong một demo**, nhưng test nghiệp vụ không nên yêu cầu `counter == 2` cho mọi mode/JDK/pipeline. Hãy test `exists == true`, và nếu cần test việc dừng sớm trong một ví dụ tuần tự cụ thể thì ghi rõ phạm vi của minh họa.

### 16.3. Nếu cần xử lý đủ mọi phần tử

Không dùng anyMatch/limit/findFirst làm đại diện cho một vòng xử lý bắt buộc với toàn nguồn. Hãy thiết kế một bước thực thi riêng (ví dụ một phương thức xử lý từng phần tử có kiểm soát), xử lý lỗi và transaction nếu cần, rồi kiểm thử số bản ghi thành công/thất bại qua **kết quả được định nghĩa**, không phải side effect tùy tiện trong predicate.

### 16.4. Khi có exception

Nếu predicate ném exception trong khi một terminal đang đánh giá nó, pipeline có thể kết thúc thất bại. Với short-circuit, một số phần tử phía sau **có thể không được đánh giá**, nên lỗi tiềm ẩn ở chúng có thể không xuất hiện trong lượt gọi đó.

Không nên hiểu “không ném lỗi” của anyMatch là toàn bộ dữ liệu đã hợp lệ. Nếu nghiệp vụ cần xác thực **mọi phần tử và ghi nhận mọi lỗi**, phải dùng quy trình kiểm tra toàn bộ với mô hình kết quả thích hợp.

## 17. Sai lầm thường gặp

| Nhầm lẫn | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| `anyMatch` đã chạy mọi predicate | Nó có thể dừng khi tìm thấy true | Dùng nó để trả boolean, không làm audit |
| `allMatch` trên rỗng phải false | Chân trị rỗng trả true | Kiểm tra yêu cầu “ít nhất một phần tử” riêng |
| `noneMatch` trên rỗng phải false | Không có phần tử thỏa, nên true | Hiểu logic lượng từ |
| `findAny` luôn trả phần tử đầu | Không bảo đảm phần tử đầu | Dùng findFirst khi cần encounter order |
| `findFirst` luôn chỉ đọc một phần tử nguồn | Có thể đứng sau filter/sorted | Xét toàn pipeline |
| `limit(2).filter` giống `filter.limit(2)` | Thứ tự làm thay đổi kết quả | Thiết kế theo ý nghĩa yêu cầu |
| `takeWhile` giống filter | takeWhile dừng ở phần tử đầu không thỏa trong ordered stream | Dùng đúng tiền tố |
| `dropWhile` bỏ mọi phần tử thỏa | Nó chỉ bỏ tiền tố trong ordered stream | Dùng filter phủ định nếu muốn bỏ mọi phần tử thỏa |
| `sorted().findFirst` luôn rẻ | Sort thường cần xét toàn bộ đầu vào | Cân nhắc min/max nếu chỉ cần cực trị |
| `peek` luôn chạy với mọi phần tử | Count có thể tối ưu mà không duyệt | Tách hiệu ứng bắt buộc |
| `parallel().anyMatch` dừng tất cả thread ngay | Công việc đang chạy có thể tiếp tục | Không dựa vào số callback |
| Bỏ qua null khi findFirst/findAny | Optional không chứa null | Lọc null/validation theo hợp đồng |
| Dùng callback để sửa collection nguồn | Vi phạm non-interference | Tách mutation khỏi Stream |
| Gọi lại cùng một Stream sau terminal | Stream đã bị tiêu thụ | Tạo stream mới từ nguồn |

## 18. Bài tập tự luyện

### Bài 1: Kết quả với stream rỗng

Dự đoán:

~~~java
IntStream.empty().anyMatch(n -> n > 0);
IntStream.empty().allMatch(n -> n > 0);
IntStream.empty().noneMatch(n -> n > 0);
~~~

**Đáp án:** lần lượt **false**, **true**, **true**. Không phải vì một predicate đã chạy, mà vì định nghĩa logic của ba phép match trên tập rỗng.

### Bài 2: So sánh filter + limit

Nguồn **[1, 2, 3, 4, 5, 6]**:

~~~java
numbers.stream().filter(n -> n % 2 == 0).limit(2).toList();
numbers.stream().limit(2).filter(n -> n % 2 == 0).toList();
~~~

**Đáp án:** **[2,4]** và **[2]**. Hai pipeline trả kết quả khác nhau.

### Bài 3: takeWhile với điều kiện xuất hiện lại

Nguồn **[1,2,5,2,1]**, predicate `n < 5`. Hãy tính takeWhile, dropWhile và filter.

**Đáp án:**

- `takeWhile` → **[1,2]**.
- `dropWhile` → **[5,2,1]**.
- `filter` → **[1,2,2,1]**.

### Bài 4: Tìm bản ghi đầu tiên theo thời gian

Bạn cần chọn **giao dịch sớm nhất có status=SUCCESS**. Có thể gọi `transactions.stream().filter(success).findFirst()` ngay không?

**Đáp án:** chỉ khi **encounter order của transactions** đã đúng thứ tự thời gian tăng dần. Nếu chưa, phải sắp theo thời gian hoặc dùng một phép cực trị phù hợp. Không giả định Stream tự biết “sớm nhất” theo ngày giao dịch.

### Bài 5: Kiểm toán tất cả phần tử

Một chương trình viết:

~~~java
boolean found = orders.stream()
        .peek(thisService::audit)
        .anyMatch(Order::isUrgent);
~~~

**Hỏi:** Có bảo đảm audit được ghi cho mọi đơn không?

**Đáp án:** **không**. anyMatch có thể dừng khi gặp một đơn khẩn cấp và một số lời gọi peek chưa chạy; ngoài ra Stream có thể tối ưu các thao tác khi kết quả không cần chúng. Hãy thiết kế bước audit riêng với hợp đồng lỗi rõ ràng nếu audit là yêu cầu bắt buộc.

### Bài 6: Chọn phép toán tối ưu về ý nghĩa

Để biết một danh sách có phần tử vi phạm hạn mức hay không, nên dùng `anyMatch`, `filter(...).toList().size()>0` hay `sorted().findFirst()`?

**Đáp án gợi ý:** `anyMatch(violatesLimit)` diễn đạt câu hỏi boolean trực tiếp nhất và cho phép dừng sớm khi đủ thông tin. Không tạo List hoặc sort toàn bộ chỉ để trả lời có/không.

## 19. Ghi nhớ

**Thao tác ngắn mạch có thể đưa ra kết quả mà không cần tiêu thụ toàn bộ nguồn.** Trong Stream Java:

- **anyMatch** dừng khi đủ bằng chứng true; **allMatch** dừng khi gặp false; **noneMatch** dừng khi gặp true.
- **allMatch/noneMatch trên stream rỗng là true**, còn anyMatch là false.
- **findFirst** tôn trọng encounter order khi có; **findAny** không hứa trả phần tử đầu.
- **limit** và **takeWhile** có thể giới hạn phần tử đi tiếp; **dropWhile** bỏ tiền tố rồi tiếp tục chuyển phần còn lại.
- **sorted/distinct** có trạng thái, nên thao tác ngắn mạch phía sau không bảo đảm chỉ cần duyệt một phần tử gốc.
- **Một số callback có thể không chạy** vì short-circuit hoặc tối ưu, ví dụ count có thể bỏ qua peek/map khi kích thước đã được biết.
- **Parallel short-circuit không bảo đảm dừng mọi callback tức thì**; không dựa vào thứ tự hoặc số lượt gọi.
- **Predicate phải non-interfering, stateless** khi có thể, và không gắn với hiệu ứng bắt buộc.

Khi đọc một pipeline, hãy hỏi: **terminal cần kết quả gì, cần bao nhiêu dữ liệu để kết luận, có bước stateful nào đứng trước, và liệu việc bỏ qua callback có làm sai yêu cầu nghiệp vụ không?** Đây là cách nhận diện và khai thác short-circuit vừa hiệu quả vừa chính xác.
