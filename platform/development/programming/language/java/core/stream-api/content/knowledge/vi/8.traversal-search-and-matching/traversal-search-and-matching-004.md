# Kiểm tra điều kiện bằng anyMatch, allMatch và noneMatch

> **Chương:** Duyệt, tìm kiếm và đối sánh  
> **Module:** JAVA_STREAM_API  
> **Trọng tâm:** Ba thao tác kết thúc trả về `boolean` của Java Stream API: `anyMatch`, `allMatch` và `noneMatch`. Chúng kiểm tra điều kiện trên các phần tử theo kiểu khai báo, tận dụng pipeline lazy và có thể dừng sớm (*short-circuit*).

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích chính xác ý nghĩa của `anyMatch`, `allMatch` và `noneMatch` thông qua lượng từ “tồn tại”, “mọi” và “không tồn tại”.
2. Dự đoán kết quả trên Stream có phần tử và **Stream rỗng**, kể cả trường hợp đã lọc hết phần tử.
3. Phân biệt kết quả `boolean` của ba thao tác với kết quả `Optional` của `findFirst`/`findAny`.
4. Mô tả tính **terminal**, **short-circuit**, thứ tự đánh giá và hành vi trong Stream song song.
5. Xây dựng predicate an toàn, không can thiệp nguồn, và diễn đạt những điều kiện kết hợp hoặc lồng nhau.
6. Chọn đúng API cho bài toán kiểm tra hợp lệ, phát hiện lỗi, xác nhận dữ liệu và tìm kiếm.
7. Nhận diện bẫy về trạng thái chia sẻ, nguồn vô hạn, Stream dùng một lần và tài nguyên I/O.

Ví dụ dùng Java 17. Các thao tác `anyMatch`, `allMatch`, `noneMatch` và các phiên bản trên primitive Stream có từ Java 8; những ví dụ dùng `List.of` cần Java 9+ và `Stream.toList` (nếu xuất hiện) cần Java 16+. Các đoạn mã ngắn nằm trong ngữ cảnh phương thức, trừ khi ví dụ khai báo lớp hoàn chỉnh.

## 1. Ba câu hỏi khác nhau trên cùng một Stream

Giả sử danh sách điểm số là `[7, 8, 10, 5]`. Ta muốn hỏi:

- **Có ít nhất một điểm đạt 10 không?** Dùng `anyMatch`.
- **Tất cả điểm có từ 0 đến 10 không?** Dùng `allMatch`.
- **Có chắc không điểm nào âm không?** Dùng `noneMatch`.

~~~java
import java.util.List;

List<Integer> scores = List.of(7, 8, 10, 5);

boolean hasPerfectScore = scores.stream()
        .anyMatch(score -> score == 10);

boolean allInRange = scores.stream()
        .allMatch(score -> score >= 0 && score <= 10);

boolean noNegativeScore = scores.stream()
        .noneMatch(score -> score < 0);

System.out.println(hasPerfectScore); // true
System.out.println(allInRange);       // true
System.out.println(noNegativeScore);  // true
~~~

Ba phương thức đều nhận một **predicate**: một hàm trả về `true` hoặc `false` cho mỗi phần tử. Chúng là **terminal operations** (thao tác kết thúc), trả về **một** giá trị `boolean` và tiêu thụ Stream.

| Phương thức | Câu hỏi với predicate `P` | Kết quả `true` khi nào? | Có thể dừng ngay khi… |
|---|---|---|---|
| `anyMatch(P)` | Có **ít nhất một** phần tử thỏa `P`? | Tồn tại phần tử có `P(x) == true` | Gặp phần tử thỏa `P` |
| `allMatch(P)` | **Mọi** phần tử đều thỏa `P`? | Không có phần tử nào vi phạm `P` | Gặp phần tử **không** thỏa `P` |
| `noneMatch(P)` | **Không có** phần tử nào thỏa `P`? | Không tồn tại phần tử thỏa `P` | Gặp phần tử thỏa `P` |

Với một nguồn hữu hạn, nếu chưa gặp điều kiện để dừng sớm, thao tác phải xem xét đủ phần tử cần thiết để kết luận. Không có phương thức nào trả về danh sách phần tử khớp: kết quả của chúng luôn là `boolean`.

## 2. Ý nghĩa logic: tồn tại, mọi và không tồn tại

Ký hiệu tập phần tử mà Stream sẽ cung cấp là `S`, và `P(x)` là điều kiện áp dụng lên phần tử `x`:

| Java | Biểu thức logic | Đọc bằng lời |
|---|---|---|
| `stream.anyMatch(P)` | \(\exists x \in S: P(x)\) | Tồn tại ít nhất một `x` làm `P` đúng |
| `stream.allMatch(P)` | \(\forall x \in S: P(x)\) | Với mọi `x` trong nguồn, `P` đều đúng |
| `stream.noneMatch(P)` | \(\nexists x \in S: P(x)\) | Không tồn tại `x` nào làm `P` đúng |

Các lượng từ này giải thích ngay hành vi dừng sớm:

- Để chứng minh **tồn tại**, chỉ cần một phần tử thỏa.
- Để bác bỏ **mọi phần tử đều thỏa**, chỉ cần một phản ví dụ.
- Để bác bỏ **không tồn tại**, chỉ cần tìm một phần tử thỏa.

Ví dụ:

~~~java
import java.util.List;

List<Integer> values = List.of(2, 4, 7, 8);

boolean anyOdd  = values.stream().anyMatch(n -> n % 2 != 0);
boolean allEven = values.stream().allMatch(n -> n % 2 == 0);
boolean noZero  = values.stream().noneMatch(n -> n == 0);

System.out.println(anyOdd);  // true  — có 7
System.out.println(allEven); // false — 7 là phản ví dụ
System.out.println(noZero);  // true  — không có 0
~~~

**Phân biệt ý nghĩa:** `noneMatch(P)` là “không có phần tử nào thỏa `P`”, còn `allMatch(P)` là “mọi phần tử thỏa `P`”. Chúng không phải hai cách viết cho cùng một câu hỏi.

## 3. Trường hợp dễ sai nhất: Stream rỗng

Xét Stream **không chứa phần tử nào**:

~~~java
import java.util.stream.Stream;

System.out.println(Stream.<Integer>empty()
        .anyMatch(n -> n > 0));   // false

System.out.println(Stream.<Integer>empty()
        .allMatch(n -> n > 0));   // true

System.out.println(Stream.<Integer>empty()
        .noneMatch(n -> n > 0));  // true
~~~

Bảng kết quả:

| Nguồn sau các thao tác trung gian | `anyMatch(P)` | `allMatch(P)` | `noneMatch(P)` |
|---|---|---|---|
| Stream rỗng | **false** | **true** | **true** |
| Có phần tử và tất cả đều thỏa `P` | true | true | false |
| Có phần tử và không phần tử nào thỏa `P` | false | false | true |
| Có phần tử và một số thỏa, một số không | true | false | false |

**Vì sao `allMatch` trên Stream rỗng trả về `true`?** Không có phần tử nào phản bác phát biểu “mọi phần tử đều thỏa”. Trong logic, đó là **chân lý rỗng** (*vacuous truth*). Tương tự, không có phần tử nào thỏa predicate, nên `noneMatch` là `true` và `anyMatch` là `false`.

Không có yêu cầu gọi predicate trên một Stream rỗng; thực tế không có phần tử nào để truyền vào predicate.

### 3.1. Lọc hết phần tử cũng tạo ra trường hợp rỗng

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 3);

boolean result = values.stream()
        .filter(n -> n > 100)
        .allMatch(n -> n % 2 == 0);

System.out.println(result); // true
~~~

Kết quả `true` ở đây **không có nghĩa** là chương trình tìm được số chẵn trên 100. Pipeline `filter` đã loại hết phần tử; `allMatch` nhận một Stream rỗng và trả `true`.

### 3.2. Nếu nghiệp vụ đòi hỏi ít nhất một phần tử, hãy nói rõ

Ví dụ, “mọi mã sản phẩm phải hợp lệ **và danh sách phải có ít nhất một mã**”:

~~~java
import java.util.List;

List<String> productCodes = List.of("SP01", "SP02");

boolean validBatch = !productCodes.isEmpty()
        && productCodes.stream()
                .allMatch(code -> code.startsWith("SP"));

System.out.println(validBatch); // true
~~~

Với `List.of()`, `validBatch` sẽ là `false`, vì đã kiểm tra điều kiện **không rỗng** riêng. Nếu nguồn chỉ là một Stream dùng một lần, không nên gọi `count()` rồi `allMatch()` trên **cùng đối tượng Stream**: thao tác kết thúc đầu tiên đã tiêu thụ nó. Khi cần cả thông tin “không rỗng” và “mọi phần tử hợp lệ” trên nguồn một lượt, cân nhắc thiết kế một phép tổng hợp phù hợp hoặc kiểm tra từ nguồn có thể duyệt lại.

### 3.3. noneMatch trên rỗng cũng đúng

~~~java
import java.util.List;

List<String> names = List.of();

boolean noBlankNames = names.stream()
        .noneMatch(String::isBlank);

System.out.println(noBlankNames); // true
~~~

Điều này chỉ xác nhận **không phát hiện tên rỗng**; nó không xác nhận danh sách có tên. Cần tách yêu cầu “không được trống” khỏi yêu cầu “không có phần tử vi phạm”.

## 4. Terminal operation và short-circuit vận hành ra sao?

`anyMatch`, `allMatch`, `noneMatch` đều là **short-circuiting terminal operations**. Chúng **có thể** kết thúc trước khi duyệt hết phần tử, khi đã đủ thông tin để quyết định kết quả.

Ví dụ quan sát trong **Stream tuần tự có thứ tự**:

~~~java
import java.util.List;

List<Integer> numbers = List.of(2, 5, 8, 13);

boolean found = numbers.stream()
        .anyMatch(n -> {
            System.out.println("Kiểm tra: " + n);
            return n > 6;
        });

System.out.println("Kết quả: " + found);
~~~

Với pipeline tuần tự trên `List` này, kết quả minh họa:

~~~text
Kiểm tra: 2
Kiểm tra: 5
Kiểm tra: 8
Kết quả: true
~~~

Phần tử `13` không cần được kiểm tra: `8 > 6` đã chứng minh được “có ít nhất một phần tử thỏa”.

Hai trường hợp tương tự:

~~~java
import java.util.List;

List<Integer> numbers = List.of(2, 5, 8, 13);

boolean allSmall = numbers.stream()
        .allMatch(n -> n < 10); // false khi gặp 13

boolean noneEqualFive = numbers.stream()
        .noneMatch(n -> n == 5); // false khi gặp 5

System.out.println(allSmall);     // false
System.out.println(noneEqualFive);// false
~~~

**Phải hiểu “có thể dừng sớm” đúng phạm vi:** kết quả `boolean` được bảo đảm theo hợp đồng; số phần tử được đánh giá, thứ tự gọi predicate và thời điểm hủy việc đang chạy **không phải giao ước để logic nghiệp vụ dựa vào**, nhất là trong Stream song song. Đoạn `println` chỉ phục vụ quan sát trên pipeline tuần tự.

### 4.1. Thao tác trung gian lazy, thao tác matching kích hoạt pipeline

~~~java
import java.util.List;
import java.util.stream.Stream;

List<String> names = List.of("An", "Bình", "Chi");

Stream<String> pipeline = names.stream()
        .filter(name -> name.length() >= 2)
        .map(String::toUpperCase);

boolean hasBinh = pipeline.anyMatch("BÌNH"::equals);

System.out.println(hasBinh); // true
~~~

`filter` và `map` thiết lập pipeline; `anyMatch` kích hoạt duyệt khi cần. Sau đó, biến `pipeline` đã bị tiêu thụ và **không thể dùng thêm** cho một terminal operation khác.

Muốn chạy kiểm tra khác, tạo Stream **mới** từ `names`:

~~~java
boolean allNonBlank = names.stream().allMatch(name -> !name.isBlank());
boolean noVeryLong = names.stream().noneMatch(name -> name.length() > 20);
~~~

## 5. anyMatch: tìm kiếm sự tồn tại

`anyMatch(P)` phù hợp với câu hỏi dạng “có phần tử nào…?” hoặc “có ít nhất một…?”.

### 5.1. Phát hiện đơn hàng vượt ngưỡng

~~~java
import java.util.List;

record Order(String id, long totalVnd) {}

List<Order> orders = List.of(
        new Order("DH-01", 200_000),
        new Order("DH-02", 1_600_000),
        new Order("DH-03", 850_000)
);

boolean hasLargeOrder = orders.stream()
        .anyMatch(order -> order.totalVnd() > 1_000_000);

System.out.println(hasLargeOrder); // true
~~~

Đây là phép kiểm tra tồn tại; không cần xây danh sách đơn hàng lớn chỉ để biết nó có ít nhất một phần tử hay không. Khi cần **chính đơn hàng** vượt ngưỡng, dùng `filter(...).findFirst()` hoặc `filter(...).findAny()` để nhận `Optional<Order>`.

### 5.2. Các phần tử phải thỏa nhiều điều kiện cùng lúc

~~~java
boolean hasLargePriorityOrder = orders.stream()
        .anyMatch(order -> order.id().startsWith("DH-")
                && order.totalVnd() >= 1_500_000);

System.out.println(hasLargePriorityOrder); // true
~~~

Đối với mỗi đơn hàng, predicate kết hợp hai điều kiện bằng `&&`. Nếu cần đọc rõ hơn, tách thành `Predicate<Order>` riêng. Toán tử `&&` của Java cũng dừng đánh giá biểu thức con bên phải nếu biểu thức bên trái `false`.

### 5.3. Phân biệt với đếm tất cả phần tử khớp

~~~java
long expensiveCount = orders.stream()
        .filter(order -> order.totalVnd() > 1_000_000)
        .count(); // 1
~~~

`count` trả về số lượng, còn `anyMatch` trả về `boolean`. Khi chỉ cần biết **có hay không**, `anyMatch` biểu đạt trực tiếp mục đích và có thể dừng sớm.

## 6. allMatch: kiểm tra tính hợp lệ toàn bộ

`allMatch(P)` phù hợp với yêu cầu “mọi phần tử phải…” hoặc “không phần tử nào vi phạm điều kiện chuẩn”.

### 6.1. Kiểm tra dữ liệu nhập

~~~java
import java.util.List;

List<String> emails = List.of(
        "an@example.com",
        "binh@example.org",
        "chi@example.net"
);

boolean allHaveAtSign = emails.stream()
        .allMatch(email -> email.contains("@"));

System.out.println(allHaveAtSign); // true
~~~

Ví dụ chỉ minh họa predicate, **không phải thuật toán xác thực email đầy đủ**. Trong ứng dụng thực tế, dùng quy tắc kiểm tra phù hợp với miền nghiệp vụ.

### 6.2. Phát hiện một phần tử không hợp lệ khiến cả đợt thất bại

~~~java
import java.util.List;

List<Integer> quantities = List.of(3, 5, 0, 2);

boolean allPositive = quantities.stream()
        .allMatch(quantity -> quantity > 0);

System.out.println(allPositive); // false
~~~

`0` là phản ví dụ đầu tiên trong dãy. Với Stream tuần tự, sau phản ví dụ, việc kiểm tra thêm `2` không cần thiết để xác định kết quả. Với dữ liệu chưa biết số lượng, đây là phép kiểm tra gọn và không cần giữ một danh sách các lỗi.

### 6.3. Kết hợp “có phần tử” và “tất cả hợp lệ”

Nếu yêu cầu “có ít nhất một đơn hàng và **mọi** đơn hàng có tổng dương”, hãy viết hai điều kiện:

~~~java
import java.util.List;

List<Order> orders = List.of(
        new Order("DH-01", 100_000),
        new Order("DH-02", 200_000)
);

boolean validOrderBatch = !orders.isEmpty()
        && orders.stream().allMatch(order -> order.totalVnd() > 0);

System.out.println(validOrderBatch); // true
~~~

Ở đây giả sử `record Order(String id, long totalVnd) {}` đã được khai báo như ví dụ trước. Việc đặt yêu cầu **không rỗng** trước `allMatch` tránh bẫy chân lý rỗng.

## 7. noneMatch: xác nhận không có phần tử bị cấm

`noneMatch(P)` được dùng khi `P` mô tả **điều không được phép xuất hiện**.

~~~java
import java.util.List;

List<String> fileNames = List.of(
        "report.csv", "summary.txt", "orders.json"
);

boolean noExecutable = fileNames.stream()
        .noneMatch(name -> name.endsWith(".exe"));

System.out.println(noExecutable); // true
~~~

Đây chỉ là một kiểm tra đuôi tên, không phải giải pháp kiểm tra loại tệp đáng tin cậy về bảo mật.

### 7.1. Cách đặt predicate tránh đọc ngược ý

~~~java
import java.util.List;

List<Integer> quantities = List.of(2, 4, 7);

boolean noneNegative = quantities.stream()
        .noneMatch(q -> q < 0);

boolean allNonNegative = quantities.stream()
        .allMatch(q -> q >= 0);

System.out.println(noneNegative);    // true
System.out.println(allNonNegative);  // true
~~~

Hai câu có nghĩa logic tương đương nếu `q < 0` và `q >= 0` là hai điều kiện phủ định của nhau trên miền dữ liệu. Cách nào dễ đọc hơn phụ thuộc ngôn ngữ nghiệp vụ:

- “Không có số lượng âm” → `noneMatch(q -> q < 0)`.
- “Mọi số lượng đều không âm” → `allMatch(q -> q >= 0)`.

### 7.2. Kiểm tra sự thiếu vắng của trạng thái lỗi

~~~java
import java.util.List;

enum State { NEW, ACTIVE, BLOCKED }

List<State> states = List.of(State.NEW, State.ACTIVE, State.ACTIVE);

boolean hasNoBlocked = states.stream()
        .noneMatch(state -> state == State.BLOCKED);

System.out.println(hasNoBlocked); // true
~~~

Nếu có một `State.BLOCKED`, `noneMatch` có thể kết luận `false` ngay tại phần tử đó.

## 8. Quan hệ phủ định và định luật De Morgan

Đặt `P` là một predicate ổn định, không có tác dụng phụ; các biểu thức sau tương đương **về kết quả** khi áp dụng trên cùng một dãy phần tử:

| Biểu thức | Tương đương |
|---|---|
| `noneMatch(P)` | `!anyMatch(P)` |
| `noneMatch(P)` | `allMatch(not P)` |
| `allMatch(P)` | `!anyMatch(not P)` |
| `anyMatch(P)` | `!allMatch(not P)` |

Ví dụ cụ thể, ba cách diễn đạt “không có số âm”:

~~~java
import java.util.List;

List<Integer> numbers = List.of(2, 4, 6);

boolean byNoneMatch = numbers.stream()
        .noneMatch(n -> n < 0);

boolean byNegation = !numbers.stream()
        .anyMatch(n -> n < 0);

boolean byAllMatch = numbers.stream()
        .allMatch(n -> n >= 0);

System.out.println(byNoneMatch == byNegation); // true
System.out.println(byNoneMatch == byAllMatch); // true
~~~

**Chú ý:** mỗi biểu thức dùng `numbers.stream()` để tạo một Stream riêng. Không thể dùng cùng một đối tượng `Stream` cho nhiều terminal operation.

Các đẳng thức logic vẫn đúng với Stream **rỗng**: `noneMatch(P) == true`, `anyMatch(P) == false`, `allMatch(not P) == true`.

### 8.1. Dùng Predicate.not khi dễ hiểu hơn

`Predicate.not` có từ Java 11 và hữu ích khi phủ định method reference:

~~~java
import java.util.List;
import java.util.function.Predicate;

List<String> labels = List.of("A", "B", "C");

boolean allNonBlank = labels.stream()
        .allMatch(Predicate.not(String::isBlank));

System.out.println(allNonBlank); // true
~~~

`Predicate.not(String::isBlank)` tạo predicate phủ định của `String::isBlank`. Đây là một cách viết dễ đọc hơn việc tạo một lambda riêng chỉ để đặt dấu `!` trước lời gọi phương thức.

### 8.2. Không nhầm anyMatch và allMatch là hai giá trị đối nghịch

~~~java
import java.util.List;

List<Integer> values = List.of(1, -1);

boolean anyPositive = values.stream().anyMatch(n -> n > 0);
boolean allPositive = values.stream().allMatch(n -> n > 0);

System.out.println(anyPositive); // true
System.out.println(allPositive); // false
~~~

Điều kiện “có số dương” và “mọi số đều dương” có thể cùng `true`, cùng `false` (trên Stream rỗng: `false` và `true`), hoặc khác nhau. Vì thế **không** có quy tắc chung rằng `allMatch(P) == !anyMatch(P)`.

## 9. Ghép predicate và pipeline cho dễ đọc

`Predicate<T>` có các phép kết hợp `and`, `or`, `negate`. Chúng cho phép đặt tên điều kiện khi logic trở nên dài.

~~~java
import java.util.List;
import java.util.function.Predicate;

record Candidate(String name, int years, boolean active) {}

List<Candidate> candidates = List.of(
        new Candidate("An", 3, true),
        new Candidate("Bình", 1, false),
        new Candidate("Chi", 5, true)
);

Predicate<Candidate> experienced = c -> c.years() >= 3;
Predicate<Candidate> isActive = Candidate::active;

boolean hasEligibleCandidate = candidates.stream()
        .anyMatch(experienced.and(isActive));

boolean noneActiveWithoutExperience = candidates.stream()
        .noneMatch(isActive.and(experienced.negate()));

System.out.println(hasEligibleCandidate);          // true
System.out.println(noneActiveWithoutExperience);    // true
~~~

Ở đây, `Predicate.and` và `Predicate.or` sử dụng cách đánh giá ngắn mạch tương tự `&&` và `||` của Java. Với predicate thuần, việc tách tên giúp dễ đọc và kiểm thử hơn. Đừng dựa vào side effect xảy ra ở vế phải: vế đó có thể không được gọi nếu đã biết kết quả.

### 9.1. Kiểm tra “mọi phần tử được lọc đều hợp lệ”

~~~java
import java.util.List;

record Product(String code, boolean active, int stock) {}

List<Product> products = List.of(
        new Product("A", true, 5),
        new Product("B", false, -2),
        new Product("C", true, 3)
);

boolean allActiveHaveStock = products.stream()
        .filter(Product::active)
        .allMatch(p -> p.stock() >= 0);

System.out.println(allActiveHaveStock); // true
~~~

Điều kiện ở đây có nghĩa: **mọi sản phẩm đang hoạt động đều có tồn kho không âm**. Nó **không** kiểm tra tồn kho của sản phẩm không hoạt động.

Nếu không có sản phẩm nào đang hoạt động, `allMatch` trên dòng sau `filter` trả `true`. Nếu nghiệp vụ yêu cầu “phải có ít nhất một sản phẩm hoạt động và tất cả đều hợp lệ”, cần thêm kiểm tra tồn tại:

~~~java
boolean hasActive = products.stream().anyMatch(Product::active);

boolean activeBatchValid = hasActive && products.stream()
        .filter(Product::active)
        .allMatch(p -> p.stock() >= 0);
~~~

Vì `products` là `List` nên có thể tạo hai Stream mới. Với nguồn chỉ duyệt một lần, cần một thiết kế tổng hợp phù hợp thay vì cố tái sử dụng cùng Stream.

## 10. Kiểm tra cấu trúc lồng nhau bằng các lượng từ

Các thao tác matching có thể lồng trong nhau, nhưng **thứ tự lượng từ làm thay đổi ý nghĩa bài toán**.

Giả sử mỗi đơn hàng chứa nhiều dòng sản phẩm:

~~~java
import java.util.List;

record Item(String sku, int quantity) {}
record Order(String id, List<Item> items) {}

List<Order> orders = List.of(
        new Order("O-01", List.of(
                new Item("PEN", 2),
                new Item("BOOK", 1))),
        new Order("O-02", List.of(
                new Item("BAG", 0))),
        new Order("O-03", List.of())
);
~~~

### 10.1. Có ít nhất một đơn hàng có dòng không hợp lệ?

~~~java
boolean hasOrderWithInvalidItem = orders.stream()
        .anyMatch(order -> order.items().stream()
                .anyMatch(item -> item.quantity() <= 0));

System.out.println(hasOrderWithInvalidItem); // true (O-02)
~~~

Ở đây là **tồn tại đơn hàng** mà trong đó **tồn tại dòng** có số lượng không dương. Đơn hàng `O-03` rỗng không có dòng nào để phát hiện lỗi theo biểu thức này.

### 10.2. Mọi đơn hàng đều chứa ít nhất một dòng hợp lệ?

~~~java
boolean everyOrderHasPositiveItem = orders.stream()
        .allMatch(order -> order.items().stream()
                .anyMatch(item -> item.quantity() > 0));

System.out.println(everyOrderHasPositiveItem); // false
~~~

`O-02` chỉ có dòng số lượng `0`, `O-03` không có dòng; cả hai đều khiến predicate theo đơn hàng trả `false`.

### 10.3. Mọi đơn hàng có ít nhất một dòng và mọi dòng đều hợp lệ?

~~~java
boolean fullyValid = !orders.isEmpty()
        && orders.stream().allMatch(order ->
                !order.items().isEmpty()
                && order.items().stream().allMatch(item -> item.quantity() > 0));

System.out.println(fullyValid); // false
~~~

Cần kiểm tra **hai cấp không rỗng** nếu bài toán yêu cầu:

1. Phải có ít nhất một đơn hàng.
2. Mỗi đơn hàng phải có ít nhất một dòng sản phẩm.
3. Mọi dòng sản phẩm của mỗi đơn hàng có số lượng dương.

Cách viết thuần `orders.stream().allMatch(order -> order.items().stream().allMatch(...))` sẽ cho `true` với một đơn hàng rỗng, vì `allMatch` lồng bên trong đúng trên Stream rỗng. Đây là lỗi nghiệp vụ rất dễ bỏ sót.

### 10.4. “Không có đơn hàng nào chứa hàng cấm” có thể diễn đạt hai cách

~~~java
boolean noForbiddenSku = orders.stream()
        .noneMatch(order -> order.items().stream()
                .anyMatch(item -> "BANNED".equals(item.sku())));

boolean everyOrderClean = orders.stream()
        .allMatch(order -> order.items().stream()
                .noneMatch(item -> "BANNED".equals(item.sku())));
~~~

Cả hai tương đương về mặt logic trên cùng dữ liệu ổn định. Chọn cách đọc gần sát câu chữ nghiệp vụ để tránh đảo nhầm `anyMatch` và `noneMatch` ở các cấp.

## 11. Phân biệt matching với filter, findFirst, findAny và count

Cùng một yêu cầu “có số lớn hơn 100”, nhưng mỗi API phục vụ kết quả khác nhau:

| Nhu cầu | API thích hợp | Kiểu kết quả |
|---|---|---|
| Chỉ cần biết có ít nhất một phần tử khớp | `anyMatch(P)` | `boolean` |
| Xác nhận mọi phần tử hợp lệ | `allMatch(P)` | `boolean` |
| Xác nhận không có phần tử bị cấm | `noneMatch(P)` | `boolean` |
| Lấy phần tử phù hợp đầu tiên theo encounter order (nếu nguồn có thứ tự) | `filter(P).findFirst()` | `Optional<T>` |
| Lấy một phần tử phù hợp bất kỳ | `filter(P).findAny()` | `Optional<T>` |
| Đếm tất cả phần tử phù hợp | `filter(P).count()` | `long` |
| Lấy danh sách phần tử phù hợp | `filter(P).toList()` | `List<T>` (Java 16+) |

~~~java
import java.util.List;
import java.util.Optional;

List<Integer> values = List.of(12, 101, 35, 150);

boolean exists = values.stream()
        .anyMatch(n -> n > 100);

Optional<Integer> first = values.stream()
        .filter(n -> n > 100)
        .findFirst();

long count = values.stream()
        .filter(n -> n > 100)
        .count();

System.out.println(exists);            // true
System.out.println(first.orElse(-1));  // 101
System.out.println(count);             // 2
~~~

`anyMatch` không cho biết phần tử nào khớp; `findFirst` và `findAny` không bảo đảm tìm “tất cả phần tử khớp”; `count` mới cung cấp số lượng. Chọn theo **loại thông tin** thực sự cần, thay vì luôn lọc và gom về List.

Nếu chỉ cần một `boolean`, `anyMatch(P)` thường rõ hơn `filter(P).findAny().isPresent()`; hai cách có cùng mục đích tìm sự tồn tại, nhưng `anyMatch` biểu đạt ý định trực tiếp.

## 12. Primitive Stream: IntStream, LongStream và DoubleStream

Không phải lúc nào dữ liệu cũng là `Stream<Integer>` hay `Stream<Double>`. Với Stream chuyên biệt cho kiểu nguyên thủy, các phương thức matching tương ứng nhận predicate chuyên biệt:

| Stream | Kiểu predicate | Ví dụ |
|---|---|---|
| `IntStream` | `IntPredicate` | `anyMatch(n -> n < 0)` |
| `LongStream` | `LongPredicate` | `allMatch(n -> n >= 0)` |
| `DoubleStream` | `DoublePredicate` | `noneMatch(x -> Double.isNaN(x))` |

Ví dụ:

~~~java
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import java.util.stream.DoubleStream;

boolean hasMultipleOfSeven = IntStream.rangeClosed(1, 20)
        .anyMatch(n -> n % 7 == 0);

boolean allPositive = LongStream.of(2L, 7L, 100L)
        .allMatch(n -> n > 0L);

boolean noNaN = DoubleStream.of(1.5, 2.0, 3.25)
        .noneMatch(x -> Double.isNaN(x));

System.out.println(hasMultipleOfSeven); // true
System.out.println(allPositive);        // true
System.out.println(noNaN);              // true
~~~

Primitive Stream giúp tránh chi phí boxing/unboxing khi xử lý giá trị số lượng lớn. Tuy nhiên, không thể kết luận nó luôn nhanh hơn mọi thiết kế khác nếu chưa xét chi phí pipeline, nguồn dữ liệu, phép toán và JDK thực tế.

### 12.1. Chú ý giá trị NaN

Với `double`, các phép so sánh thông thường có thể gây bất ngờ nếu gặp `NaN`:

~~~java
import java.util.stream.DoubleStream;

boolean allNonNegative = DoubleStream.of(1.0, Double.NaN)
        .allMatch(x -> x >= 0.0);

System.out.println(allNonNegative); // false
~~~

`Double.NaN >= 0.0` là `false`. Khi kiểm tra dữ liệu số thực, hãy xác định nghiệp vụ có cho phép `NaN`, vô cực hoặc các giá trị đặc biệt khác không, rồi kết hợp predicate tương ứng.

## 13. Predicate thuần, dữ liệu null và lỗi thực thi

Các thao tác matching nhận một hành vi phải **non-interfering** và **stateless** theo hợp đồng Stream:

- **Non-interfering:** không thay đổi nguồn dữ liệu theo cách không được nguồn hỗ trợ khi Stream đang duyệt.
- **Stateless:** kết quả của predicate không phụ thuộc trạng thái có thể thay đổi trong quá trình pipeline chạy.

### 13.1. Tránh sửa nguồn bên trong predicate

~~~java
import java.util.ArrayList;
import java.util.List;

List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3));

// Không nên:
// numbers.stream().anyMatch(n -> {
//     numbers.add(n * 10); // Can thiệp vào chính nguồn đang duyệt
//     return n == 2;
// });
~~~

Làm như vậy có thể gây hành vi không ổn định, ngoại lệ hoặc kết quả không đúng với kỳ vọng. Một predicate nên diễn đạt phép kiểm tra; việc thêm, xóa hay sửa nguồn nên đặt ở bước xử lý phù hợp khác.

### 13.2. Side effect khiến bạn hiểu sai số lần chạy predicate

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

List<Integer> numbers = List.of(2, 5, 8, 13);
AtomicInteger calls = new AtomicInteger();

boolean found = numbers.stream().anyMatch(n -> {
    calls.incrementAndGet(); // Chỉ minh họa, không dùng cho nghiệp vụ
    return n > 6;
});

System.out.println(found);       // true
System.out.println(calls.get()); // 3 với pipeline tuần tự đã nêu
~~~

Khi chuyển sang Stream song song, thời điểm, thứ tự và tổng số lời gọi predicate có thể khác. `AtomicInteger` có thể làm bộ đếm cập nhật nguyên tử, nhưng **không** khiến một predicate có side effect trở thành stateless. Nếu cần ghi nhận mọi bản ghi, ba thao tác matching không phải nơi thích hợp vì chúng có thể dừng sớm.

### 13.3. Null phải được quyết định rõ trong predicate

`List.of(...)` không cho phép phần tử `null`, nhưng một số collection khác có thể chứa `null`. Gọi phương thức trên phần tử `null` có thể gây `NullPointerException`:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

List<String> names = new ArrayList<>(
        Arrays.asList("An", null, "Chi")
);

// Tránh nếu dữ liệu có thể chứa null:
// names.stream().allMatch(String::isBlank);
~~~

Cách kiểm tra “mọi tên phải khác null và không rỗng”:

~~~java
boolean allValid = names.stream()
        .allMatch(name -> name != null && !name.isBlank());

System.out.println(allValid); // false
~~~

Cách `filter(Objects::nonNull).allMatch(...)` **bỏ qua** các phần tử null thay vì xác định chúng không hợp lệ. Hai cách có ý nghĩa nghiệp vụ khác nhau. Chú ý: nếu lọc bỏ toàn bộ phần tử, `allMatch` trả `true` vì nguồn sau lọc rỗng.

### 13.4. Ngoại lệ từ predicate

~~~java
import java.util.List;

List<String> tokens = List.of("12", "bad", "4");

// Có thể ném NumberFormatException khi gặp "bad":
// boolean hasLarge = tokens.stream()
//         .anyMatch(token -> Integer.parseInt(token) > 10);
~~~

Nếu dữ liệu không bảo đảm đúng định dạng, cần chính sách xử lý lỗi: kiểm tra trước, từ chối dữ liệu không hợp lệ, hoặc mô hình hóa lỗi thành giá trị rõ ràng. Không nên phụ thuộc vào việc short-circuit tình cờ bỏ qua phần tử gây lỗi, vì khi thay thứ tự, điều kiện hoặc chế độ chạy song song, việc đánh giá có thể khác.

## 14. Matching trên Stream song song và nguồn không có thứ tự

~~~java
import java.util.List;

List<Integer> values = List.of(1, 5, 8, 13, 21);

boolean found = values.parallelStream()
        .anyMatch(n -> n > 10);

System.out.println(found); // true
~~~

Với predicate thuần, kết quả `true` là điều mong đợi vì có phần tử `13` và `21` thỏa. Tuy nhiên:

1. Nhiều phần tử có thể được kiểm tra **đồng thời**.
2. Một số phần tử có thể đã bắt đầu được xử lý trước khi một thread tìm thấy kết quả.
3. Số lượt kiểm tra và thứ tự gọi predicate **không được đảm bảo** giống Stream tuần tự.
4. `anyMatch` trả lời *có hay không*, nên không có khái niệm “phải tìm phần tử đầu tiên” như `findFirst`.
5. `allMatch`, `noneMatch` cũng có thể dừng sớm ở mức kết quả, nhưng không nên dùng chúng để điều khiển một tác dụng phụ cần diễn ra đúng một lần trên mỗi phần tử.

`unordered()` có thể cho framework thêm tự do bỏ encounter order khi điều đó hợp lệ. Với ba thao tác chỉ trả `boolean` và predicate stateless, việc đảo thứ tự các phần tử không làm đổi kết quả toán học trên nguồn hữu hạn, ổn định. Điều này **không đảm bảo** pipeline song song sẽ nhanh hơn; chi phí chia công việc, phối hợp thread và tính chất `Spliterator` của nguồn có thể làm chậm bài toán nhỏ.

### 14.1. Không suy ra thứ tự xử lý từ kết quả

~~~java
import java.util.List;

List<String> values = List.of("a", "b", "c", "d");

boolean exists = values.parallelStream()
        .anyMatch(s -> s.equals("b"));
~~~

Kết quả là `true`, nhưng không có bảo đảm predicate được gọi trước tiên với `"a"`. Nếu cần truy xuất phần tử đầu tiên theo encounter order, dùng `filter(...).findFirst()` trên một nguồn có thứ tự; đó là bài toán khác với matching.

## 15. Nguồn vô hạn, dừng sớm và khả năng hoàn tất

Vì các thao tác matching là **short-circuiting**, đôi khi chúng có thể xử lý được Stream vô hạn:

~~~java
import java.util.stream.IntStream;

boolean found = IntStream.iterate(0, n -> n + 1)
        .anyMatch(n -> n == 5);

System.out.println(found); // true
~~~

Trong Stream tuần tự này, khi gặp `5`, `anyMatch` có thể kết thúc. Nhưng short-circuit **không đồng nghĩa chắc chắn kết thúc**. Nếu không bao giờ xuất hiện yếu tố quyết định, một nguồn vô hạn có thể khiến terminal operation chạy mãi:

~~~java
import java.util.stream.Stream;

// Tránh chạy: không có phản ví dụ nào để allMatch dừng.
// Stream.generate(() -> "ok")
//         .allMatch("ok"::equals);

// Tránh chạy: không có phần tử thỏa để noneMatch dừng.
// Stream.generate(() -> "ok")
//         .noneMatch("bad"::equals);

// Tránh chạy: không có phần tử thỏa để anyMatch dừng.
// Stream.generate(() -> "ok")
//         .anyMatch("bad"::equals);
~~~

Nếu nghiệp vụ chỉ muốn xét một số phần tử đầu, hãy áp dụng `limit` trước matching:

~~~java
import java.util.stream.Stream;

boolean firstHundredOk = Stream.generate(() -> "ok")
        .limit(100)
        .allMatch("ok"::equals);

System.out.println(firstHundredOk); // true
~~~

Lúc này câu hỏi thực sự là: “100 phần tử đầu có đều là `"ok"` không?”. Đừng nhầm với việc xác nhận **toàn bộ** một nguồn có thể vô hạn. Tương tự, `takeWhile` và các cơ chế cắt giới hạn khác chỉ giúp hoàn tất khi điều kiện dừng được đáp ứng theo nguồn và thứ tự phù hợp.

## 16. Matching với Stream đọc tệp: quản lý tài nguyên

`Files.lines` tạo `Stream<String>` lấy dữ liệu từ tệp, có tài nguyên hệ thống cần đóng. Matching có thể dừng sớm, nhưng thao tác kết thúc **không tự thay thế việc đóng Stream I/O**.

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path logFile = Path.of("application.log");

try (Stream<String> lines = Files.lines(logFile, StandardCharsets.UTF_8)) {
    boolean hasError = lines.anyMatch(line -> line.contains("ERROR"));
    System.out.println("Có dòng lỗi: " + hasError);
} catch (IOException | UncheckedIOException e) {
    System.err.println("Không đọc được tệp: " + e.getMessage());
}
~~~

Điều cần nhớ:

- `Files.lines` tạo nguồn đọc dòng theo nhu cầu.
- `anyMatch` dừng sớm khi đã phát hiện một dòng thỏa điều kiện; không bắt buộc tải toàn bộ tệp vào `List`.
- `try-with-resources` bảo đảm gọi `close()` khi rời khối, kể cả lúc matching trả `true` sớm.
- `IOException` có thể xảy ra khi mở nguồn; lỗi đọc trong khi tiêu thụ Stream có thể được bọc trong `UncheckedIOException`.
- Nếu muốn tiếp tục xử lý các dòng khác sau khi tìm thấy kết quả, cần mở/tạo một Stream mới theo yêu cầu và vòng đời của nguồn.

Các kiến thức này liên hệ với phần xử lý tài nguyên, `Spliterator`, Stream song song và hiệu năng trong module. Chọn terminal operation đúng chỉ là một nửa câu chuyện: nguồn có được đóng và phép kiểm tra có đủ độc lập để chạy theo pipeline hay không cũng cần được xét.

## 17. Bảng quyết định nhanh

| Yêu cầu nghiệp vụ | Biểu thức gợi ý | Điểm cần lưu ý |
|---|---|---|
| Có ít nhất một đơn vượt 1 triệu? | `anyMatch(order -> order.totalVnd() > 1_000_000)` | Chỉ trả `boolean` |
| Mọi đơn đều có tổng dương? | `allMatch(order -> order.totalVnd() > 0)` | Trả `true` nếu Stream rỗng |
| Không đơn nào có số lượng âm? | `noneMatch(order -> order.quantity() < 0)` | Predicate mô tả điều bị cấm |
| Mọi phần tử hợp lệ **và danh sách không rỗng**? | `!list.isEmpty() && list.stream().allMatch(P)` | Kiểm tra không rỗng riêng |
| Có lỗi nào trong dữ liệu? | `anyMatch(isInvalid)` | Có thể dừng ngay khi thấy lỗi |
| Không có lỗi nào? | `noneMatch(isInvalid)` | Tương đương `allMatch(isValid)` nếu phủ định chính xác |
| Tìm chính phần tử lỗi đầu tiên? | `filter(isInvalid).findFirst()` | Trả `Optional<T>` |
| Đếm tổng số lỗi? | `filter(isInvalid).count()` | Phải xác định số lượng |
| Kiểm tra các dòng của tệp? | `Files.lines(...).anyMatch(P)` | Dùng `try-with-resources` |
| Kiểm tra phần tử trong nhiều lớp cấu trúc? | Matching lồng nhau | Cẩn thận lượng từ và rỗng ở từng lớp |

## 18. Bài tập củng cố

### Bài 1. Dự đoán ba kết quả

~~~java
import java.util.List;

List<Integer> values = List.of(3, 6, 9);

System.out.println(values.stream().anyMatch(n -> n % 2 == 0));
System.out.println(values.stream().allMatch(n -> n > 0));
System.out.println(values.stream().noneMatch(n -> n > 10));
~~~

**Đáp án:** `true`, `true`, `true`. Có một số chẵn (`6`); tất cả đều dương; không có số nào lớn hơn 10.

### Bài 2. Stream rỗng và chân lý rỗng

~~~java
import java.util.List;

List<Integer> empty = List.of();

System.out.println(empty.stream().anyMatch(n -> n < 0));
System.out.println(empty.stream().allMatch(n -> n < 0));
System.out.println(empty.stream().noneMatch(n -> n < 0));
~~~

**Đáp án:** `false`, `true`, `true`. Không có phần tử nào làm predicate đúng, không có phản ví dụ cho `allMatch`, và không có phần tử nào vi phạm điều kiện “none”.

### Bài 3. Viết điều kiện “mọi tên không rỗng và có ít nhất một tên”

**Đề:** Cho `List<String> names`, các phần tử có thể rỗng hoặc chứa toàn dấu cách. Kết quả phải là `false` nếu `names` rỗng.

**Đáp án tham khảo:**

~~~java
boolean valid = !names.isEmpty()
        && names.stream().allMatch(name -> !name.isBlank());
~~~

Nếu danh sách có thể chứa `null`, thêm `name != null &&` vào predicate.

### Bài 4. Phủ định bằng De Morgan

**Đề:** Viết lại `!values.stream().anyMatch(n -> n < 0)` bằng đúng một matching operation khác và không có toán tử phủ định bên ngoài.

**Đáp án:**

~~~java
boolean noNegative = values.stream().noneMatch(n -> n < 0);
~~~

Có thể viết `values.stream().allMatch(n -> n >= 0)` nếu miền dữ liệu cho phép coi hai điều kiện là phủ định chính xác.

### Bài 5. Lượng từ lồng nhau

**Đề:** Bạn có danh sách `orders` từ mục 10. Kiểm tra “có ít nhất một đơn hàng mà mọi dòng trong đơn đó đều có số lượng dương **và đơn đó không rỗng**”.

**Đáp án tham khảo:**

~~~java
boolean existsFullyPositiveOrder = orders.stream()
        .anyMatch(order -> !order.items().isEmpty()
                && order.items().stream()
                        .allMatch(item -> item.quantity() > 0));

System.out.println(existsFullyPositiveOrder); // true (O-01)
~~~

Điều kiện `!order.items().isEmpty()` loại trường hợp đơn hàng rỗng `O-03` có thể làm `allMatch` bên trong trả `true` một cách không phù hợp với yêu cầu nghiệp vụ.

### Bài 6. Vì sao dùng cùng Stream hai lần thất bại?

~~~java
import java.util.List;
import java.util.stream.Stream;

Stream<Integer> source = List.of(1, 2, 3).stream();

boolean hasTwo = source.anyMatch(n -> n == 2);
// boolean allPositive = source.allMatch(n -> n > 0);
// Dòng trên biên dịch nhưng sẽ ném IllegalStateException khi chạy.
~~~

**Đáp án:** `anyMatch` là terminal operation đã tiêu thụ `source`. Phải tạo Stream mới từ `List` (hoặc thiết kế một lần duyệt duy nhất nếu nguồn chỉ đọc một lượt).

### Bài 7. Tác dụng phụ trong parallel stream

**Đề:** Có nên dùng `AtomicInteger counter` tăng ở mỗi lời gọi predicate trong `parallelStream().anyMatch(...)` để đếm tất cả phần tử không?

**Đáp án:** Không. `anyMatch` được phép dừng khi đủ thông tin, nên predicate không buộc chạy trên tất cả phần tử; chế độ song song cũng không bảo đảm thứ tự và số lần gọi như một vòng lặp tuần tự. `AtomicInteger` chỉ hỗ trợ tính nguyên tử của cập nhật, không biến phép kiểm tra thành phép đếm toàn bộ. Nếu cần số lượng, dùng `count` phù hợp.

### Bài 8. Chọn API đúng

**Đề:** Bạn muốn trả về **mã đơn hàng đầu tiên** có tổng tiền âm, nếu có. `anyMatch` có đủ không?

**Đáp án:** Không. `anyMatch` chỉ trả `boolean`. Dùng:

~~~java
import java.util.List;
import java.util.Optional;

record Order(String id, long totalVnd) {}

List<Order> orders = List.of(
        new Order("DH-01", 100_000),
        new Order("DH-02", -50_000),
        new Order("DH-03", 20_000)
);

Optional<String> firstInvalidId = orders.stream()
        .filter(order -> order.totalVnd() < 0)
        .map(Order::id)
        .findFirst();

System.out.println(firstInvalidId.orElse("Không có")); // DH-02
~~~

Ví dụ này dùng `Order` có các accessor `id()` và `totalVnd()` như ở mục 5, tách biệt với cấu trúc đơn hàng có `items()` ở mục 10. Nếu không cần giữ thứ tự đầu tiên, cân nhắc `findAny()`.

---

**Ghi nhớ:** `anyMatch` hỏi **có ít nhất một**, `allMatch` hỏi **tất cả**, còn `noneMatch` hỏi **không có phần tử nào** thỏa predicate. Cả ba là **short-circuiting terminal operations** trả về `boolean`. Trên Stream rỗng, kết quả lần lượt là **false – true – true**. Hãy viết predicate stateless/non-interfering, quản lý vòng đời Stream I/O, tạo Stream mới cho phép kiểm tra độc lập và thêm điều kiện “không rỗng” khi nghiệp vụ yêu cầu.

