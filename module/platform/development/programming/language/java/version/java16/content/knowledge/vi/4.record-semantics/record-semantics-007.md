# Vì sao record vẫn là đối tượng có identity và không mặc nhiên là value-based class

**Module:** `JAVA_VERSION_JAVA16`  
**Chương:** Ngữ nghĩa record  
**Áp dụng:** Java 16 trở lên, bao gồm Java hiện đại.

Record được giới thiệu để biểu diễn dữ liệu theo giá trị: các component có tên xác định trạng thái của đối tượng, còn compiler cung cấp `equals` và `hashCode` mặc định dựa trên component. Vì vậy, hai record khác instance nhưng có cùng lớp và cùng giá trị component có thể bằng nhau theo `equals`.

Tuy nhiên, **record vẫn là một class Java có object identity**. Mỗi instance vẫn có danh tính đối tượng riêng; `==` vẫn kiểm tra hai tham chiếu có cùng trỏ đến một instance hay không. Record cũng không tự động trở thành một *value-based class* theo khái niệm của Java API/JEP 390. Hiểu rõ sự khác biệt này giúp tránh nhầm lẫn khi dùng record với đồng bộ hóa, collection, cache và API phụ thuộc identity.

## 1. Record mang value semantics nhưng vẫn có object identity

Xét hai record có cùng component:

```java
record Point(int x, int y) {}

Point first = new Point(3, 5);
Point second = new Point(3, 5);
Point alias = first;

System.out.println(first.equals(second)); // true
System.out.println(first == second);      // false

System.out.println(first.equals(alias));  // true
System.out.println(first == alias);       // true
```

`first` và `second` là hai instance khác nhau, nhưng bằng nhau theo giá trị vì chúng cùng lớp record `Point` và có các component tương ứng bằng nhau. `alias` là một tham chiếu khác cùng trỏ đến instance của `first`, nên cả `equals` và `==` đều trả về `true`.

Hai câu hỏi này cần được phân biệt:

- **Value equality:** hai đối tượng có cùng giá trị theo hợp đồng `equals` hay không?
- **Object identity:** hai tham chiếu có trỏ đến đúng cùng một đối tượng hay không?

Sơ đồ:

```text
first  ─────┐
            ├────> Point instance A (x=3, y=5)
alias  ─────┘

second ──────────> Point instance B (x=3, y=5)

A.equals(B) = true
A == B       = false
```

Record cung cấp cách so sánh theo giá trị tiện lợi; điều đó không làm hai instance riêng biệt trở thành một instance duy nhất.

## 2. Vì sao record vẫn là object có identity?

Record là một dạng class đặc biệt:

- Record class là class ngầm định `final`, không thể được kế thừa.
- Record class kế thừa từ `java.lang.Record`.
- Các trường ứng với record component là `final`.
- Instance record vẫn là object tham chiếu trong Java, có thể được gán cho biến tham chiếu, truyền vào phương thức và so sánh bằng `==`.
- Instance record vẫn tham gia các cơ chế identity của object như `System.identityHashCode` và monitor dùng bởi `synchronized`.

Ví dụ:

```java
record CustomerKey(String customerId) {}

CustomerKey key1 = new CustomerKey("C-100");
CustomerKey key2 = new CustomerKey("C-100");

System.out.println(key1 == key2);       // false
System.out.println(key1.equals(key2));  // true
System.out.println(System.identityHashCode(key1));
System.out.println(System.identityHashCode(key2));
```

`System.identityHashCode` trả về mã băm identity của object, không gọi implementation `hashCode()` do record cung cấp. Hai instance khác nhau vẫn có thể có cùng identity hash vì va chạm là hợp lệ. Do đó, đây không phải ID duy nhất và cũng không phải cách kiểm tra identity thay cho `==`.

Không nên hiểu identity là địa chỉ bộ nhớ vật lý. JVM có thể di chuyển hoặc tối ưu hóa cách lưu trữ object trong khi vẫn bảo toàn hành vi quan sát được theo đặc tả Java. Ứng dụng chỉ nên dựa vào các phép toán identity mà Java cung cấp, không suy luận địa chỉ từ mã băm hoặc kết quả `==`.

## 3. Value-based class là khái niệm gì?

Java API sử dụng khái niệm *value-based class* cho những lớp mà instance được thiết kế để được xem như giá trị có thể thay thế cho nhau khi bằng nhau. Tài liệu API của các lớp thuộc nhóm này khuyến cáo không dựa vào identity của instance.

Một số đặc điểm thường gặp:

- Các instance bằng nhau theo `equals` có thể được dùng thay thế cho nhau trong ứng dụng.
- Không nên dùng phép so sánh tham chiếu `==` để kiểm tra bằng nhau về mặt nghiệp vụ.
- Không nên dùng instance làm monitor khóa đồng bộ (`synchronized`).
- Không nên dựa vào identity hash hoặc các thao tác identity-sensitive khác.
- API có thể không bảo đảm mỗi lần tạo giá trị bằng nhau sẽ tạo một instance mới, duy nhất.

Ví dụ quen thuộc về các lớp được tài liệu Java mô tả theo value-based semantics gồm các lớp wrapper nguyên thủy như `Integer`, `Long`, `Double`, `Optional` và nhiều lớp trong `java.time`. Hãy đọc tài liệu của từng API để biết chính xác khuyến cáo áp dụng.

```java
Integer a = Integer.valueOf(1000);
Integer b = Integer.valueOf(1000);

System.out.println(a.equals(b)); // true

// Không dùng == để kiểm tra hai giá trị Integer có bằng nhau hay không.
System.out.println(a == b); // Không phải phép kiểm tra value equality.
```

Với value-based class, ứng dụng cần dựa vào hợp đồng giá trị của API, không dựa vào việc hai lần tạo giá trị có cho cùng một tham chiếu hay không.

## 4. Record khác value-based class ở điểm nào?

Record cũng khuyến khích so sánh dữ liệu bằng `equals`, nhưng record class **không mặc nhiên thuộc nhóm value-based class**. Ngữ nghĩa của record vẫn giữ object identity theo mô hình object Java.

| Đặc điểm | Record mặc định | Value-based class |
| --- | --- | --- |
| Mục tiêu thiết kế | Carrier cho dữ liệu với component có tên và value semantics mặc định. | Biểu diễn giá trị, instance bằng nhau có thể thay thế cho nhau. |
| `equals` | Thường được compiler sinh từ lớp record và component. | Theo hợp đồng giá trị do lớp định nghĩa. |
| `==` | Kiểm tra cùng instance như object Java thông thường. | Không nên dùng để kiểm tra giá trị; identity-sensitive behavior không được khuyến khích. |
| Identity của object | Có và có thể quan sát qua các API identity. | Không nên dựa vào identity; API có thể hạn chế hoặc cảnh báo thao tác identity-sensitive. |
| Dùng làm monitor `synchronized` | Về mặt ngôn ngữ có thể, nhưng thường nên dùng lock riêng. | Không nên đồng bộ hóa trên instance value-based. |
| `IdentityHashMap` | Có thể dùng khi thuật toán thực sự cần phân biệt instance record. | Không nên dùng như cách lưu trữ giá trị theo hợp đồng value-based. |

Điểm cốt lõi: *value semantics* mô tả cách một kiểu định nghĩa bình đẳng; *value-based class* là một khái niệm API có thêm khuyến cáo về việc không phụ thuộc identity. Hai khái niệm có liên quan nhưng không đồng nghĩa.

## 5. Không nhầm record với value object trong thiết kế ứng dụng

Trong thiết kế hướng đối tượng, cụm từ *value object* thường chỉ một đối tượng mô hình hóa một giá trị của miền nghiệp vụ. Record là công cụ phù hợp để triển khai nhiều value object vì:

- Component có tên và cố định sau khi khởi tạo.
- `equals` và `hashCode` mặc định dựa trên component.
- Không cần viết nhiều mã lặp cho các phương thức dữ liệu phổ biến.

Tuy nhiên, cách gọi *value object* trong kiến trúc ứng dụng không tự thay đổi mô hình identity của Java. Một record được dùng làm value object vẫn là object có identity. Nếu thuật toán cần so sánh theo giá trị, hãy dùng `equals`; nếu cần nhận biết cùng instance, hãy dùng `==` hoặc API identity phù hợp.

Ví dụ một value object mô tả khoảng ngày:

```java
import java.time.LocalDate;

record DateRange(LocalDate start, LocalDate end) {
    DateRange {
        if (start == null || end == null) {
            throw new IllegalArgumentException("Dates are required");
        }
        if (end.isBefore(start)) {
            throw new IllegalArgumentException("End must not precede start");
        }
    }
}

DateRange first = new DateRange(
    LocalDate.of(2026, 1, 1),
    LocalDate.of(2026, 1, 31)
);
DateRange second = new DateRange(
    LocalDate.of(2026, 1, 1),
    LocalDate.of(2026, 1, 31)
);

System.out.println(first.equals(second)); // true
System.out.println(first == second);      // false
```

Hai khoảng ngày bằng nhau theo dữ liệu nghiệp vụ, nhưng là hai instance riêng. Đây là cách dùng record bình thường và không cần loại bỏ identity của Java.

## 6. Identity vẫn ảnh hưởng đến đồng bộ hóa

Mỗi instance object có monitor riêng. `synchronized` khóa monitor của đúng instance được truyền vào, không khóa theo kết quả `equals`.

```java
record LockKey(String name) {}

LockKey first = new LockKey("cache");
LockKey second = new LockKey("cache");

System.out.println(first.equals(second)); // true
System.out.println(first == second);      // false

// Hai khối sau sử dụng hai monitor khác nhau:
synchronized (first) {
    // Đang giữ monitor của instance first.
}

synchronized (second) {
    // Đang giữ monitor của instance second.
}
```

Nếu hai luồng tự tạo hai record có cùng component rồi đồng bộ hóa trên từng instance, chúng không khóa chung một monitor. Vì vậy, không dùng record value được tạo lại theo dữ liệu làm lock dùng chung.

Về mặt ngôn ngữ, record không bị cấm làm monitor. Tuy nhiên, thiết kế rõ ràng hơn là dùng lock object có vòng đời và quyền sở hữu cụ thể:

```java
final class CacheCoordinator {
    private final Object lock = new Object();

    void update() {
        synchronized (lock) {
            // Thực hiện thao tác cần đồng bộ.
        }
    }
}
```

Một lock riêng tránh việc mã bên ngoài vô tình đồng bộ trên một record được chia sẻ như dữ liệu.

## 7. Dùng collection theo đúng semantics cần thiết

Các collection thông thường dùng equality theo hợp đồng của phần tử/khóa. Với record, `HashSet` và `HashMap` vì thế gộp các instance khác nhau nếu chúng bằng nhau theo `equals`.

```java
import java.util.HashSet;
import java.util.Set;

record ProductKey(String sku, int revision) {}

ProductKey first = new ProductKey("SKU-7", 1);
ProductKey second = new ProductKey("SKU-7", 1);

Set<ProductKey> keys = new HashSet<>();
keys.add(first);
keys.add(second);

System.out.println(keys.size()); // 1
```

Nếu thuật toán phải phân biệt từng instance dù các component giống nhau, Java cung cấp `IdentityHashMap`:

```java
import java.util.IdentityHashMap;
import java.util.Map;

record ProductKey(String sku, int revision) {}

ProductKey first = new ProductKey("SKU-7", 1);
ProductKey second = new ProductKey("SKU-7", 1);

Map<ProductKey, String> values = new IdentityHashMap<>();
values.put(first, "first instance");
values.put(second, "second instance");

System.out.println(first.equals(second)); // true
System.out.println(values.size());        // 2
```

`IdentityHashMap` so sánh khóa bằng `==` và dùng identity hash. Đây là lựa chọn chuyên biệt cho thuật toán cần theo dõi tham chiếu, chẳng hạn phát hiện object đã thăm khi duyệt đồ thị có chu trình hoặc lưu metadata gắn với từng instance. Không dùng nó thay `HashMap` trong nghiệp vụ thông thường chỉ vì record có identity.

## 8. Component mutable không làm mất identity của record

Record có các trường component `final`, nhưng bất biến này chỉ cố định tham chiếu. Nếu component trỏ đến một object mutable, trạng thái bên trong object đó vẫn có thể thay đổi:

```java
import java.util.ArrayList;
import java.util.List;

record SearchCriteria(List<String> tags) {}

List<String> tags = new ArrayList<>(List.of("java"));
SearchCriteria criteria = new SearchCriteria(tags);

tags.add("records");
System.out.println(criteria.tags()); // [java, records]
```

Việc thay đổi danh sách không tạo một instance record mới và cũng không làm record mất identity. Nó có thể làm thay đổi kết quả `equals`/`hashCode` vì các phương thức mặc định dựa vào component hiện tại.

Nếu record cần biểu diễn giá trị ổn định, hãy sao chép dữ liệu trong canonical constructor, ví dụ dùng `List.copyOf` khi phần tử cũng bất biến:

```java
import java.util.List;

record SearchCriteria(List<String> tags) {
    SearchCriteria {
        tags = List.copyOf(tags);
    }
}
```

`List.copyOf` bảo vệ cấu trúc danh sách khỏi việc sửa thông qua tham chiếu bên ngoài, nhưng không sao chép sâu các phần tử mutable. Thiết kế bất biến cần xét cả đồ thị component.

## 9. Có thể biến record thành kiểu không có identity bằng cách ghi đè `equals` không?

Không. Ghi đè `equals` không xóa object identity khỏi mô hình Java. Record vẫn là instance của class và `==` vẫn kiểm tra tham chiếu.

Ngoài ra, API `java.lang.Record` khuyến nghị giữ bất biến sao chép: nếu tạo một record mới bằng cách truyền kết quả các accessor của record cũ vào canonical constructor, record mới phải bằng record ban đầu theo `equals`. Một `equals` chỉ so sánh `this == other` sẽ không đáp ứng bất biến này khi hai instance khác nhau.

Nếu cần identity semantics làm bản chất của thực thể, hãy cân nhắc class thông thường với ID và vòng đời riêng. Nếu chỉ một thuật toán cần phân biệt instance, giữ record với value equality mặc định và dùng `==`/`IdentityHashMap` tại đúng nơi cần thiết.

## 10. Những nhầm lẫn cần tránh

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| Record có `equals` theo giá trị nên không có identity. | **Sai** | Record vẫn là object Java có identity. |
| Hai record cùng lớp và component bằng nhau có thể có `equals == true` nhưng `== false`. | **Đúng** | Value equality và identity là hai phép kiểm tra khác nhau. |
| Mọi record đều là value-based class theo khái niệm của Java API. | **Sai** | Record không mặc nhiên được phân loại là value-based class. |
| Value-based class khuyến khích dùng `==` để so sánh giá trị. | **Sai** | Cần dùng hợp đồng `equals`; tránh dựa vào identity. |
| Hai record bằng nhau theo `equals` sẽ dùng chung monitor. | **Sai** | Monitor gắn với từng instance. |
| `System.identityHashCode` luôn khác nhau cho hai instance khác nhau. | **Sai** | Identity hash có thể va chạm. |
| Có thể dùng `IdentityHashMap` để theo dõi riêng từng instance record. | **Đúng** | Collection này dùng identity thay cho value equality. |

## 11. Checklist lựa chọn thiết kế

Trước khi dùng record trong một API hoặc cấu trúc dữ liệu, hãy tự hỏi:

1. Dữ liệu cần được so sánh theo giá trị hay cần phân biệt từng instance?
2. Có đang nhầm value object theo kiến trúc với value-based class theo khái niệm API Java không?
3. Có dùng `==`, `identityHashCode` hoặc `synchronized` trên record mà không thật sự cần identity không?
4. Collection đang dùng `equals`/`hashCode` hay identity?
5. Component có mutable khiến giá trị equality thay đổi sau khi tạo không?
6. Nếu cần entity identity, class thông thường với ID riêng có diễn tả rõ hơn không?

**Ghi nhớ:** Record cung cấp value semantics mặc định qua `equals` và `hashCode`, nhưng vẫn là object có identity trong Java. Không mặc nhiên xem record là value-based class. Dùng `equals` cho bình đẳng dữ liệu; chỉ dùng identity-sensitive API khi thuật toán thực sự cần phân biệt instance.

## Tài liệu chính thức

- [Java SE 26 API — `java.lang.Record`, hợp đồng record và bất biến sao chép](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Record.html).
- [Java SE 26 API — `java.lang` package, value-based classes](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/package-summary.html).
- [Java SE 26 API — `java.util.IdentityHashMap`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/IdentityHashMap.html).
- [JEP 390 — Warnings for Value-Based Classes](https://openjdk.org/jeps/390).
- [JEP 395 — Records, tính năng chính thức trong Java 16](https://openjdk.org/jeps/395).
- [Java Language Specification, Section 8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.10).
