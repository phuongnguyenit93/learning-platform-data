# Thiết kế lambda ngắn, rõ nghĩa và không giấu tác dụng phụ trong Java

Lambda là cách viết phần triển khai của một functional interface tại vị trí cần truyền hành vi. Từ Java 8 đến Java hiện đại, lambda hữu ích nhất khi **người đọc nhận ra ngay dữ liệu đi vào, công việc được thực hiện và kết quả được trả về**. Cú pháp ngắn tự nó không bảo đảm mã dễ hiểu: một lambda một dòng nhưng sửa trạng thái từ bên ngoài, gọi dịch vụ mạng hoặc xử lý lỗi âm thầm có thể khó bảo trì hơn một phương thức được đặt tên.

Bài này tập trung vào **cách thiết kế lambda ngắn, rõ ý nghĩa, phân biệt phép tính với tác dụng phụ và đặt tác dụng phụ ở ranh giới dễ quan sát**. Những nguyên tắc vẫn áp dụng cho Java 17+, Stream API, callback, `Comparator` và các functional interface hiện đại.

## 1. Bắt đầu từ hợp đồng của functional interface

Một lambda được biên dịch trong ngữ cảnh một *target type* là functional interface, ví dụ:

| Functional interface | Hợp đồng | Ví dụ hành vi |
| --- | --- | --- |
| `Predicate<T>` | `boolean test(T)` | Giữ đơn hàng hợp lệ, kiểm tra quyền |
| `Function<T,R>` | `R apply(T)` | Chuẩn hóa chuỗi, tính nhãn hiển thị |
| `UnaryOperator<T>` | `T apply(T)` | Biến đổi giá trị cùng kiểu |
| `Comparator<T>` | `int compare(T,T)` | So sánh để sắp xếp |
| `Consumer<T>` | `void accept(T)` | Gửi thông báo, xuất kết quả có chủ đích |
| `Supplier<T>` | `T get()` | Cung cấp một giá trị khi cần |

Nhìn vào target type trước khi viết body. Với `Predicate`, biểu thức nên chỉ trả lời **đúng/sai**; với `Function`, body nên tập trung **biến đổi đầu vào thành đầu ra**; còn `Consumer` thể hiện một thao tác có thể có tác dụng phụ vì hợp đồng của nó không trả giá trị. Đây là định hướng thiết kế, không phải hạn chế mà ngôn ngữ Java tự cưỡng chế.

```java
Predicate<String> hasText = s -> s != null && !s.trim().isEmpty();
Function<String, String> normalize = s -> s.trim().toLowerCase(Locale.ROOT);
Consumer<String> print = System.out::println;
```

Đây là **các đoạn minh họa**, không phải một chương trình độc lập; cần import `java.util.Locale` và `java.util.function.*`. Đặt tên `hasText` và `normalize` giúp mục đích của hai hàm rõ hơn một tên mơ hồ như `f` hoặc `action`. Tham số lambda ngắn như `s` chấp nhận được khi ý nghĩa đã rõ; nếu có nhiều tham số cùng kiểu, hãy đặt tên cụ thể (`left`, `right`, `candidate`).

## 2. Lambda ngắn đến đâu là đủ?

Không có con số dòng cố định nào làm lambda trở nên “đẹp”. Tiêu chí hữu ích là một người đọc có thể nắm **một ý định chính** mà không phải dò qua nhiều nhánh, cập nhật trạng thái hoặc xử lý lỗi không liên quan.

**Nên dùng thân biểu thức** cho một phép chuyển đổi hoặc điều kiện trực tiếp:

```java
Predicate<Integer> isPositive = n -> n > 0;
Function<String, Integer> length = String::length;
Comparator<String> byLength = Comparator.comparingInt(String::length);
```

Ví dụ chỉ minh họa; cần import `java.util.Comparator` và `java.util.function.*`. Method reference như `String::length` nên dùng khi nó dễ đọc hơn một lambda tương đương.

**Dùng thân khối lệnh** nếu các bước trung gian làm logic rõ hơn, nhưng đừng cố giữ mọi thứ trong lambda:

```java
Function<String, String> label = raw -> {
    String cleaned = raw == null ? "" : raw.trim();
    if (cleaned.isEmpty()) {
        return "(trống)";
    }
    return cleaned.toUpperCase(Locale.ROOT);
};
```

Đây là đoạn minh họa cần `Function` và `Locale`. Mã hợp lệ, nhưng nếu bước chuẩn hóa được tái sử dụng hoặc quy tắc ngày càng dài, nên chuyển logic vào phương thức `formatLabel` rồi viết `Function<String,String> label = MyClass::formatLabel;`. **Chi phí hiểu mã** và sự tách biệt trách nhiệm quan trọng hơn số ký tự.

Dấu hiệu nên tách một phương thức có tên: lambda phải giải thích bằng bình luận dài; có nhiều cấp lồng `if`; lặp lại ở nhiều nơi; phải xử lý nhiều ngoại lệ; hoặc cùng lúc tính kết quả, ghi log, cập nhật database và thay đổi UI. Một phương thức nhỏ có tên tốt giúp kiểm thử không cần dựng toàn bộ pipeline hay callback.

## 3. Nhận diện tác dụng phụ thay vì chỉ nhìn vào giá trị trả về

*Tác dụng phụ* (*side effect*) là ảnh hưởng quan sát được ngoài giá trị mà hàm trả về, chẳng hạn ghi vào danh sách ngoài, thay đổi field, cập nhật database, gọi mạng, ghi file, in console hoặc thay đổi bộ đếm. Tác dụng phụ không phải lúc nào cũng sai: nghiệp vụ phải lưu dữ liệu, gửi thông báo và ghi log. Vấn đề nảy sinh khi một lambda **trông giống phép lọc/biến đổi** nhưng âm thầm thay đổi nơi khác.

So sánh hai ý định:

```java
// Chuyển đổi giá trị: kết quả phụ thuộc rõ ràng vào input.
Function<Integer, Integer> doubled = n -> n * 2;

// Cập nhật trạng thái ngoài: hiệu quả phụ thuộc vào ngữ cảnh.
List<Integer> history = new ArrayList<>();
Function<Integer, Integer> hiddenWrite = n -> {
    history.add(n);
    return n * 2;
};
```

Đây là đoạn minh họa, cần import `java.util.List`, `java.util.ArrayList` và `java.util.function.Function`. `history` được lambda capture hợp lệ vì **biến tham chiếu** không bị gán lại; nhưng **nội dung danh sách vẫn mutable**. “Effectively final” của biến cục bộ không có nghĩa đối tượng mà nó tham chiếu là bất biến hoặc thread-safe.

Lambda không có tác dụng phụ thường dễ kiểm thử bằng cặp đầu vào–đầu ra, dễ tái sử dụng và phù hợp hơn với các API có thể tối ưu hóa hay chạy song song. Phép toán thực sự *pure* còn phải tránh phụ thuộc vào trạng thái toàn cục biến đổi hoặc đồng hồ hệ thống: một lambda không ghi gì nhưng đọc `System.currentTimeMillis()` cũng có kết quả phụ thuộc vào môi trường.

**Câu hỏi thực hành:** “Nếu gọi cùng lambda hai lần với cùng input, kết quả có thể khác vì dữ liệu bên ngoài thay đổi không? Có phần nào của chương trình bị sửa ngoài kết quả trả về không?” Câu trả lời giúp nhận diện chỗ cần tách tác dụng phụ.

## 4. Trong Stream, dùng lambda không can thiệp nguồn và ít trạng thái

Đối với các behavioral parameter của Stream như `filter`, `map`, `sorted`, hợp đồng API khuyến nghị chúng:

- **Non-interfering:** không sửa nguồn dữ liệu đang được Stream duyệt (trừ những ngoại lệ đã được tài liệu hóa của nguồn concurrent).
- **Stateless trong phần lớn trường hợp:** không phụ thuộc vào trạng thái có thể thay đổi trong thời gian pipeline chạy.

Điều kiện này quan trọng cho **cả stream tuần tự lẫn song song**, vì xử lý Stream có tính lazy và có thể được tối ưu hóa. Đừng nhầm “đang chạy sequential” với “có thể thoải mái sửa nguồn”.

### Ví dụ nguy hiểm: thay đổi danh sách đang duyệt

```java
// KHÔNG NÊN: sửa source ngay trong predicate.
// Có thể gây lỗi, kết quả bất ngờ hoặc hành vi không phù hợp hợp đồng Stream.
List<String> names = new ArrayList<>(Arrays.asList("An", "Binh", "Chi"));
names.stream()
     .filter(name -> {
         if (name.startsWith("B")) {
             names.remove(name); // can thiệp nguồn Stream
         }
         return true;
     })
     .count();
```

Đây là ví dụ **phản diện, không chạy trong ví dụ hoàn chỉnh**, dùng `java.util.*`. Nó vi phạm nguyên tắc non-interference. Thay bằng việc tính dữ liệu mới nếu cần giữ những phần tử đáp ứng điều kiện:

```java
List<String> remaining = names.stream()
        .filter(name -> !name.startsWith("B"))
        .collect(Collectors.toList());
```

Đoạn minh họa cần import `java.util.stream.Collectors`. `remaining` chứa các tên không bắt đầu bằng B, trong khi `names` không bị đụng chạm trong quá trình duyệt. Nếu yêu cầu thật sự là sửa danh sách tại chỗ, có thể dùng `names.removeIf(name -> name.startsWith("B"));` trên một danh sách mutable phù hợp, **bên ngoài một Stream đang duyệt chính danh sách đó**.

### Ví dụ nguy hiểm: dùng forEach lắp danh sách kết quả

```java
// KHÔNG NÊN: trạng thái kết quả nằm bên ngoài pipeline.
List<String> normalized = new ArrayList<>();
names.stream()
     .map(String::trim)
     .forEach(normalized::add);
```

Lối viết này có thể chạy tuần tự, nhưng đặt một tác dụng phụ không cần thiết trong việc thu thập dữ liệu; nếu đổi sang `parallelStream()` thì `ArrayList` được sửa từ nhiều luồng không an toàn, còn thứ tự ghi cũng không còn theo ý định.

```java
// NÊN: dùng collector để mô tả chính xác phép tạo kết quả.
List<String> normalized = names.stream()
        .map(String::trim)
        .collect(Collectors.toList());
```

Collector quản lý cách tích lũy kết quả theo hợp đồng của Stream. `Collectors.toList()` không hứa hẹn một kiểu danh sách cụ thể hoặc khả năng sửa đổi; nếu cần danh sách chắc chắn có thể sửa, dùng `Collectors.toCollection(ArrayList::new)`.

## 5. Tách việc biến đổi với hành động có chủ đích

Một thiết kế rõ nghĩa thường chia dòng xử lý thành hai bước:

1. **Tính toán, chọn lọc, chuyển đổi** dữ liệu bằng những hàm dễ dự đoán.
2. **Thực hiện hành động** cần thiết ở ranh giới được xác định (ghi file, gọi API, lưu database, hiển thị kết quả).

Ví dụ, khi cần gửi thông báo cho các khách hàng đủ điều kiện, hãy lấy danh sách đích bằng pipeline, sau đó gọi một phương thức có tên biểu đạt tác dụng phụ:

```java
List<String> recipients = customers.stream()
        .filter(CustomerRules::eligible)
        .map(Customer::email)
        .collect(Collectors.toList());

// Ranh giới có chủ đích: thực hiện công việc bên ngoài.
// notificationService.send(email) là phương thức minh họa của ứng dụng.
for (String email : recipients) {
    notificationService.send(email);
}
```

Đây là **mã minh họa kiến trúc**, không phải chương trình chạy độc lập: `CustomerRules`, `Customer` và `notificationService` phải được định nghĩa trong dự án thật. Tách hai giai đoạn giúp kiểm thử tập người nhận mà không gửi email thật, và giúp bổ sung retry, giới hạn tốc độ, nhật ký, giao dịch hoặc xử lý lỗi tại nơi thực sự gọi dịch vụ.

**Consumer và forEach vẫn có chỗ đứng.** `Consumer<T>` được thiết kế cho hành động không trả giá trị; `list.forEach(System.out::println)` có thể là lựa chọn đúng khi mục tiêu chính là xuất dữ liệu. Điểm cốt lõi là tác dụng phụ nên **hiển nhiên, được đặt tên và có phạm vi**, không bị giấu trong `filter`/`map` hoặc trong một hàm được kỳ vọng chỉ tính toán.

Một lời gọi để ghi log trong `map` có thể hữu ích tạm thời khi debug. Nhưng nếu nhật ký là dữ liệu bắt buộc để audit, không thể phụ thuộc vào việc Stream sẽ luôn gọi mọi behavioral parameter: thực thi có thể ngắn mạch hoặc bỏ qua giai đoạn không ảnh hưởng đến kết quả. Hãy tạo một bước audit tường minh với quy tắc thành công/lỗi và khả năng ghi nhận đáng tin cậy.

## 6. Tránh giấu trạng thái và ngoại lệ trong một lambda

### a) Trạng thái nằm ngoài body

```java
AtomicInteger index = new AtomicInteger();
Function<String, String> numbered =
        text -> index.incrementAndGet() + ": " + text;
```

Đây là đoạn minh họa cần `import java.util.concurrent.atomic.AtomicInteger;` và `Function`. `AtomicInteger` làm phép tăng có tính nguyên tử, nhưng **không biến `numbered` thành stateless**. Thứ tự gán số trong pipeline song song vẫn phụ thuộc thứ tự thực thi; đồng bộ hóa chỉ giải quyết một phần vấn đề an toàn dữ liệu, không tạo ra quy tắc sắp xếp nghiệp vụ.

Nếu cần vị trí phần tử trong danh sách, cân nhắc một vòng lặp có chỉ số rõ ràng. Nếu chỉ cần đếm kết quả, hãy dùng `count()`. Nếu cần số thứ tự ổn định, định nghĩa thứ tự đầu vào và phương pháp đánh chỉ số, không tạo bộ đếm ẩn bên trong `map`.

### b) Không nuốt lỗi để giữ lambda một dòng

```java
// KHÔNG NÊN: âm thầm biến mọi lỗi thành chuỗi rỗng.
Function<String, String> risky = key -> {
    try {
        return lookup(key); // phương thức minh họa
    } catch (Exception ignored) {
        return "";
    }
};
```

Đây là mã minh họa, không chạy độc lập vì `lookup` chưa được định nghĩa. Việc thay mọi lỗi bằng chuỗi rỗng làm mất khác biệt giữa “không có dữ liệu” và “lỗi hệ thống”; gây khó chẩn đoán, báo cáo và retry. Thay vào đó, đưa logic I/O và xử lý ngoại lệ vào phương thức riêng với hợp đồng rõ, bắt **loại ngoại lệ có chủ đích**, rồi chuyển thành kết quả lỗi hoặc ném lại theo chính sách phù hợp.

Một lambda dùng trong `Function.apply` không được tự ý ném checked exception không có trong chữ ký functional interface; cần xử lý hoặc dùng một abstraction được thiết kế để diễn đạt checked exception. Đừng bọc mọi ngoại lệ vào `RuntimeException` mà không xét ngữ cảnh và ý nghĩa nghiệp vụ.

### c) Không thực hiện nhiều tác vụ không liên quan

Nếu body cùng lúc: kiểm tra điều kiện, ghi log, đổi trạng thái đối tượng, gửi request và trả boolean, người đọc khó biết thao tác nào gây lỗi và thao tác nào được phép lặp lại. Chia các bước có tên như `validateOrder`, `calculateTotal` và `saveOrder`, rồi xử lý giao dịch và retry ngoài lambda tính toán.

## 7. Dùng method reference, helper và tên biến để giải thích ý định

So sánh hai cách khi bộ lọc đã có quy tắc nghiệp vụ:

```java
// Khó đọc hơn khi quy tắc dài dần.
orders.stream().filter(o -> o.amount() >= 80 && o.active() && !o.blocked());

// Dễ mở rộng: tên phương thức nói lên ý định.
orders.stream().filter(OrderRules::eligibleForProcessing);
```

Đây là **mã minh họa**, yêu cầu project có `Order` và `OrderRules` tương ứng; `amount()`/`active()`/`blocked()` là phương thức ví dụ của domain, không phải API JDK. Helper `eligibleForProcessing` có thể được kiểm thử độc lập với dữ liệu biên: 79, 80, khách bị khóa, đơn không hoạt động.

Method reference hữu ích khi nó đọc tự nhiên (`String::trim`, `OrderRules::eligibleForProcessing`); không bắt buộc dùng nếu một lambda ngắn rõ hơn. Tránh đặt tên kiểu `handle`, `process`, `applyRule` nếu có thể nói cụ thể hành vi nào được kiểm tra hoặc chuyển đổi.

Một phép biến đổi tốt thường có:

- Đầu vào và đầu ra xác định; tên tham số có ý nghĩa khi cần.
- Null, giá trị rỗng và dữ liệu biên được xử lý theo hợp đồng, không im lặng bỏ qua.
- Một trách nhiệm dễ mô tả bằng một câu.
- Đầu ra không phụ thuộc trạng thái ngoài có thể thay đổi trong lúc chạy.
- Hành động gây thay đổi bên ngoài được đẩy tới lớp/đoạn mã có chủ đích.

## 8. Chú ý lazy evaluation, short-circuit, parallel và peek

**Stream lười thực thi.** Ví dụ `stream.filter(...).map(...)` chỉ mô tả pipeline; dữ liệu thường được xử lý khi có terminal operation (`collect`, `count`, `findFirst`, `forEach`...). Với `findFirst` hoặc `anyMatch`, các phần tử phía sau có thể không được xét. Không nên dựa vào số lần chạy của lambda để cập nhật bộ đếm nghiệp vụ hay audit.

**Tối ưu hóa có thể bỏ qua một giai đoạn.** Tài liệu Stream cho phép runtime không gọi một behavioral parameter nếu chứng minh được kết quả pipeline không thay đổi. Chẳng hạn `peek` dùng để quan sát khi debug không phải chỗ đáng tin để ghi sự kiện bắt buộc. Trên nguồn biết trước kích thước, `count()` có thể không cần duyệt các phần tử, nên `peek(System.out::println)` có thể không in gì. Đây là hành vi hợp lệ theo API, không phải lỗi trình biên dịch.

**Parallel stream có thể đổi thứ tự và thread chạy callback.** Trong `parallelStream()`, `forEach` không cam kết thứ tự gặp phần tử; `forEachOrdered` tôn trọng encounter order khi nguồn có thứ tự, nhưng không bảo đảm xử lý nhanh. Đừng giả định `map`, `filter` hay `peek` của các phần tử sẽ chạy theo thứ tự và cùng một thread. Tránh đọc/ghi mutable state dùng chung trong các lambda này. Parallel stream chỉ phù hợp khi tác vụ đủ nặng, không can thiệp nguồn và benchmark với dữ liệu thực cho thấy lợi ích.

**Sửa input bất biến là điểm cộng thiết kế.** Ví dụ `map(String::trim)` tạo giá trị kết quả thay vì thay đổi danh sách nguồn. Với đối tượng mutable, một lambda gọi setter trong `map` vẫn là tác dụng phụ ngay cả nếu kết quả là cùng object. Khi cần thay đổi đối tượng, xác định rõ ai sở hữu nó và việc sửa có được phép trong pha xử lý này không.

## 9. Chương trình Java hoàn chỉnh: biến đổi rõ ràng, tác dụng phụ ở điểm cuối

Ví dụ sau xây báo cáo đơn hàng với quy tắc đơn có tổng tiền từ 80 trở lên. Phần biến đổi dùng `filter` và `map` đơn giản; điều kiện nghiệp vụ và cách tạo nhãn được đặt tên. Việc in và ghi nhật ký mô phỏng là hai hành động chủ đích **sau khi đã tính ra kết quả**.

Lưu vào **LambdaDesignDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.function.Consumer;
import java.util.stream.Collectors;

public class LambdaDesignDemo {
    static final class Order {
        final String code;
        final int amount;

        Order(String code, int amount) {
            this.code = code;
            this.amount = amount;
        }
    }

    private static boolean eligible(Order order) {
        return order.amount >= 80;
    }

    private static String label(Order order) {
        return order.code + ":" + order.amount;
    }

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
                new Order("A", 120),
                new Order("B", 50),
                new Order("C", 80)
        );

        List<String> report = orders.stream()
                .filter(LambdaDesignDemo::eligible)
                .map(LambdaDesignDemo::label)
                .collect(Collectors.toList());

        int total = orders.stream()
                .filter(LambdaDesignDemo::eligible)
                .mapToInt(order -> order.amount)
                .sum();

        report.forEach(System.out::println);
        System.out.println("Total: " + total);

        List<String> audit = new ArrayList<>();
        Consumer<String> recordAudit = audit::add;
        report.forEach(recordAudit);
        System.out.println("Audit records: " + audit.size());
    }
}
```

Biên dịch/chạy trên JDK 17+:

```bash
javac LambdaDesignDemo.java
java LambdaDesignDemo
```

Kết quả chuẩn:

```text
A:120
C:80
Total: 200
Audit records: 2
```

**Phân tích:** `eligible` không sửa đơn hàng và chỉ phụ thuộc giá trị đầu vào; `label` chỉ tạo chuỗi mới; `mapToInt(...).sum()` tổng hợp mà không cần biến `total` ở ngoài Stream. `Consumer<String> recordAudit = audit::add;` có tác dụng phụ rõ ràng ở pha riêng, không giấu trong `filter` hoặc `map`. Ví dụ dùng danh sách cục bộ và `forEach` tuần tự, nên thứ tự và số bản ghi như output. Trong sản phẩm thật, audit bắt buộc phải đi qua một thành phần có giao ước lưu trữ, lỗi và retry; danh sách trong bộ nhớ chỉ minh họa vị trí tách tác dụng phụ.

Chú ý `audit::add` là method reference tới `List.add` trả `boolean` nhưng tương thích với `Consumer<String>`: lời gọi phương thức là *statement expression*, kết quả `boolean` bị bỏ qua khi target type trả `void`. Đừng nhầm sự tương thích cú pháp đó với ý nghĩa “không có tác dụng phụ”.

## 10. Bảng quyết định và checklist review

| Tình huống | Cách viết nên ưu tiên | Lý do |
| --- | --- | --- |
| Lọc theo một điều kiện rõ ràng | `filter(order -> order.amount >= 80)` | Predicate ngắn và dễ hiểu |
| Quy tắc nghiệp vụ có nhiều nhánh | `filter(OrderRules::eligible)` | Tên phương thức bộc lộ mục đích, dễ test |
| Chuyển đổi từng phần tử | `map(MyFormatter::format)` | Tách chức năng tính toán với quản lý pipeline |
| Gom kết quả vào danh sách | `collect(Collectors.toList())` | Đúng vai trò collector, tránh mutation bên ngoài |
| Cần thao tác một collection tại chỗ | Chọn API collection thích hợp, như `removeIf` | Hành vi thay đổi dữ liệu là chủ đích |
| Ghi log/hiển thị/gửi thông báo | Bước riêng qua `Consumer` hoặc phương thức có tên | Điểm có tác dụng phụ dễ quan sát, dễ xử lý lỗi |
| Cần số thứ tự ổn định | Vòng lặp có chỉ số hoặc giải pháp đánh chỉ số rõ ràng | Tránh bộ đếm bị chi phối thứ tự thực thi |
| Có trạng thái shared, I/O hay checked exception | Tách helper/service và quy tắc xử lý lỗi | Không che khuất trách nhiệm trong lambda |

Khi review, lần lượt kiểm tra:

1. **Ý định:** nhìn vào functional interface, body và tên phương thức đã hiểu được mục đích chưa?
2. **Một trách nhiệm:** lambda có đang gánh nhiều việc độc lập không?
3. **Tác dụng phụ:** body có sửa source, field, collection bên ngoài hoặc gọi hệ thống ngoài mà người đọc không ngờ tới không?
4. **Đầu ra:** kết quả có thể thay đổi vì trạng thái ngoài hoặc giờ hệ thống không? Nếu có, sự phụ thuộc có được diễn đạt rõ không?
5. **Stream:** behavioral parameter có non-interfering/stateless? Pipeline có phụ thuộc vào `peek`, `forEach` hoặc thứ tự chạy ngầm định không?
6. **Lỗi:** exception, `null`, dữ liệu rỗng, retry và giao dịch có chính sách rõ không?
7. **Test:** có thể kiểm thử từng phép biến đổi mà không phải gửi thông báo, ghi database hoặc gọi mạng thật không?
8. **Hiệu năng:** đã tránh đồng bộ hóa không cần thiết và việc dùng `parallelStream()` chỉ theo cảm tính chưa?

### Bài tập thực hành

**Bài 1.** Refactor một pipeline dùng `forEach(result::add)` để dựng danh sách thành `collect(Collectors.toList())`. Giải thích vì sao phiên bản mới dễ bảo trì và an toàn hơn nếu pipeline có thể chạy song song.

**Bài 2.** Với `Predicate<Integer> valid = n -> { counter++; return n > 0; };`, hãy chỉ ra tác dụng phụ và lý do phép đếm gọi lambda không phải cách đáng tin để đếm phần tử đạt điều kiện. Gợi ý: dùng `filter` rồi `count()` nếu mục tiêu là đếm kết quả.

**Bài 3.** Tách callback vừa lấy thông tin khách hàng, vừa gửi mail, vừa trả chuỗi thành một phương thức tính dữ liệu đầu ra và một thao tác gửi mail riêng. Xác định nơi sẽ xử lý retry và lỗi kết nối.

**Bài 4.** Đọc `Function<String,String> f = s -> { log(s); return s.trim(); };`. Chỉ ra rằng `log(s)` là tác dụng phụ, và nếu nó là audit bắt buộc thì cần thiết kế một bước ghi đáng tin cậy ngoài phép biến đổi `map`.

### Tài liệu chuẩn để tra cứu

- [Java SE 25 — Stream API, behavioral parameters, side effects](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html)
- [Java SE 25 — java.util.stream, non-interference và stateless behavior](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html)
- [Java SE 25 — java.util.function](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/package-summary.html)
- [Java Language Specification — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.27)
