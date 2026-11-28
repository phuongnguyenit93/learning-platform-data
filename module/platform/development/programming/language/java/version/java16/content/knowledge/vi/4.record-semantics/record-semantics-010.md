# Điều kiện dùng record làm key trong Map hoặc phần tử trong Set

**Module:** `JAVA_VERSION_JAVA16`  
**Chương:** Ngữ nghĩa record  
**Áp dụng:** Java 16 trở lên, bao gồm Java hiện đại.

Record thường là lựa chọn phù hợp để làm khóa `Map` hoặc phần tử `Set` vì compiler tự sinh `equals(Object)` và `hashCode()` dựa trên các component. Hai instance record cùng lớp và có các component bằng nhau được xem là cùng một giá trị trong những collection sử dụng equality thông thường.

Tuy nhiên, không phải cứ khai báo `record` là có thể dùng an toàn làm khóa. Điều kiện quan trọng là **ngữ nghĩa bằng nhau phải đúng với nghiệp vụ và dữ liệu tham gia `equals`/`hashCode` phải ổn định trong suốt thời gian record nằm trong collection**. Component mutable, mảng, kiểu số có quy tắc equality đặc biệt hoặc comparator không nhất quán đều có thể tạo kết quả ngoài mong muốn.

## 1. Vì sao record phù hợp làm key hoặc Set element?

Các collection thông thường dựa trên equality:

- `HashMap` dùng `hashCode()` để định vị nhóm khóa ứng viên, sau đó dùng `equals()` để xác định khóa có bằng nhau không.
- `HashSet` dùng cùng cơ chế để tránh thêm một phần tử bằng phần tử đã có.
- Các collection có thứ tự như `TreeMap` và `TreeSet` xác định khóa/phần tử tương đương theo kết quả của `Comparator` hoặc `compareTo`.

Record tự cung cấp value equality mặc định từ các component. Ví dụ:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

record UserKey(String tenantId, String username) {}

UserKey first = new UserKey("acme", "linh");
UserKey second = new UserKey("acme", "linh");

System.out.println(first == second);      // false: hai instance
System.out.println(first.equals(second)); // true: cùng giá trị

Map<UserKey, String> users = new HashMap<>();
users.put(first, "Linh");
users.put(second, "Linh Nguyen");

System.out.println(users.size()); // 1
System.out.println(users.get(first)); // Linh Nguyen

Set<UserKey> uniqueUsers = new HashSet<>();
uniqueUsers.add(first);
uniqueUsers.add(second);
System.out.println(uniqueUsers.size()); // 1
```

Hai đối tượng `UserKey` khác instance nhưng bằng nhau theo giá trị. Vì vậy `HashMap` coi chúng là cùng một khóa; lần `put` thứ hai cập nhật giá trị ánh xạ. `HashSet` chỉ giữ một phần tử tương đương.

## 2. Điều kiện thứ nhất: equality phải đúng với ý nghĩa nghiệp vụ

Trước khi dùng record làm khóa hoặc phần tử, hãy xác định chính xác khi nào hai giá trị được xem là cùng một khóa.

Record mặc định so sánh:

1. Đối tượng ở vế phải phải thuộc cùng lớp record tại runtime.
2. Các component tương ứng phải bằng nhau theo ngữ nghĩa của kiểu component.

Ví dụ, mã khách hàng và mã đơn hàng có thể cùng biểu diễn bằng `String` nhưng không nên bị gộp thành một loại khóa:

```java
record CustomerId(String value) {}
record OrderId(String value) {}

CustomerId customerId = new CustomerId("42");
OrderId orderId = new OrderId("42");

System.out.println(customerId.value().equals(orderId.value())); // true
System.out.println(customerId.equals(orderId));                 // false
```

Đây là lợi thế của record có kiểu riêng: cùng dữ liệu thô không đồng nghĩa cùng ý nghĩa nghiệp vụ. Hãy dùng tên và kiểu component phản ánh đúng những yếu tố tạo nên danh tính của khóa.

Nếu username không phân biệt chữ hoa/chữ thường, cần quyết định chính sách chuẩn hóa trước khi tạo khóa. Có thể chuẩn hóa trong compact constructor, nhưng chỉ khi đó thực sự là quy tắc của hệ thống:

```java
import java.util.Locale;
import java.util.Objects;

record UsernameKey(String tenant, String username) {
    UsernameKey {
        tenant = Objects.requireNonNull(tenant, "tenant");
        username = Objects.requireNonNull(username, "username")
            .strip()
            .toLowerCase(Locale.ROOT);
    }
}

System.out.println(
    new UsernameKey("acme", "Linh")
        .equals(new UsernameKey("acme", " linh "))
); // true
```

Chuẩn hóa làm cho các biểu diễn tương đương theo quy tắc nghiệp vụ tạo ra cùng giá trị khóa. Không tự ý chuyển chữ thường hoặc cắt khoảng trắng nếu hệ thống nguồn coi các ký tự đó là khác nhau.

## 3. Điều kiện thứ hai: `equals` và `hashCode` phải nhất quán

Mọi khóa dùng trong `HashMap` hoặc phần tử dùng trong `HashSet` phải tuân thủ hợp đồng chung:

- Nếu `a.equals(b)` là `true` thì `a.hashCode()` và `b.hashCode()` bắt buộc bằng nhau.
- Nếu hai mã băm bằng nhau, hai đối tượng không nhất thiết bằng nhau. Va chạm hash là hợp lệ.
- Nếu thông tin tham gia `equals` không đổi, `hashCode` của đối tượng phải ổn định trong cùng lần chạy.

Với record mặc định, compiler sinh `equals` và `hashCode` thành một cặp nhất quán theo component. Nếu component là class tự viết, class đó cũng phải tuân thủ hợp đồng tương ứng.

Ví dụ component tự viết sai hợp đồng:

```java
final class BrokenCode {
    private final String value;

    BrokenCode(String value) {
        this.value = value;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof BrokenCode that
            && value.equals(that.value);
    }

    // Lỗi: kế thừa Object.hashCode(), không dựa trên value.
}

record BrokenKey(BrokenCode code) {}
```

Hai `BrokenCode` có cùng `value` có thể bằng nhau theo `equals` nhưng có mã băm identity khác nhau. Record chứa chúng cũng có thể bằng nhau nhưng có hash khác nhau, làm việc tra cứu trong hash collection không đáng tin cậy. Khi tự viết class có equality theo giá trị, hãy triển khai cả `equals` và `hashCode`.

## 4. Điều kiện thứ ba: trạng thái tham gia equality phải ổn định

Các trường component của record là `final`, nhưng object mà component tham chiếu tới có thể mutable. Nếu component là `List`, `Set` hoặc class có `equals`/`hashCode` dựa trên trạng thái mutable, thay đổi trạng thái có thể làm kết quả equality và mã băm của record thay đổi.

Ví dụ khóa có danh sách mutable:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

record SearchKey(List<String> filters) {}

List<String> filters = new ArrayList<>(List.of("active"));
SearchKey key = new SearchKey(filters);

Map<SearchKey, String> cache = new HashMap<>();
cache.put(key, "result");

filters.add("premium");

System.out.println(cache.get(key)); // Có thể không tìm thấy entry
```

Khi chèn, `HashMap` tổ chức khóa theo mã băm lúc danh sách chỉ có `"active"`. Sau đó `List.hashCode` thay đổi theo nội dung mới. Lúc tra cứu, `HashMap` dùng hash hiện tại, có thể tìm đến vùng khác với nơi entry đã được lưu. Entry vẫn có thể xuất hiện khi duyệt map, nhưng thao tác tra cứu hoặc xóa có thể thất bại.

Vì vậy, không thay đổi thông tin tham gia `equals`/`hashCode` của một khóa trong khi khóa đó đang được lưu trong `HashMap` hoặc `HashSet`.

## 5. Điều kiện thứ tư: bảo vệ component collection bằng snapshot

Với danh sách chứa phần tử bất biến như `String`, có thể tạo snapshot trong compact constructor:

```java
import java.util.List;
import java.util.Objects;

record SearchKey(List<String> filters) {
    SearchKey {
        filters = List.copyOf(
            Objects.requireNonNull(filters, "filters")
        );
    }
}
```

`List.copyOf` trả về danh sách không thể sửa qua API `List` và không phản ánh thay đổi cấu trúc về sau trên danh sách nguồn. Vì `String` là immutable, snapshot này ổn định theo nội dung:

```java
List<String> source = new java.util.ArrayList<>(List.of("active"));
SearchKey key = new SearchKey(source);

source.add("premium");
System.out.println(key.filters()); // [active]
```

Một vài điểm cần nhớ:

- `List.copyOf` không chấp nhận phần tử `null`.
- Đây là snapshot nông: danh sách được bảo vệ, nhưng object bên trong không tự được sao chép sâu.
- `Set.copyOf` và `Map.copyOf` cũng tạo collection không thể sửa, nhưng không biến các phần tử hoặc khóa/giá trị mutable thành immutable.
- `Collections.unmodifiableList(source)` chỉ là view không thể sửa qua wrapper; nếu nơi khác vẫn sửa `source`, view cũng phản ánh thay đổi. Đây không phải snapshot độc lập.

Nếu phần tử của danh sách là class mutable và `equals`/`hashCode` dựa trên trường mutable, `List.copyOf` chưa đủ. Cần chuyển chúng thành kiểu bất biến hoặc sao chép sâu theo mô hình dữ liệu.

## 6. Điều kiện thứ năm: hiểu rõ component array

Mảng Java không ghi đè `Object.equals` và `Object.hashCode`. Vì vậy record mặc định chứa mảng so sánh component theo identity của mảng:

```java
record ByteKey(byte[] bytes) {}

ByteKey first = new ByteKey(new byte[] {1, 2, 3});
ByteKey second = new ByteKey(new byte[] {1, 2, 3});

System.out.println(first.equals(second)); // false
```

Hai mảng khác tham chiếu nên hai record mặc định không bằng nhau, dù nội dung giống nhau. Nếu mảng đại diện cho một buffer cụ thể, identity có thể đúng với yêu cầu. Nếu mảng đại diện cho một giá trị như chuỗi byte, nội dung thường mới là tiêu chí mong muốn.

Khi cần equality theo nội dung, hãy ghi đè **cả** `equals` và `hashCode` bằng cặp API tương ứng (`Arrays.equals`/`Arrays.hashCode` hoặc `Arrays.deepEquals`/`Arrays.deepHashCode` cho cấu trúc lồng nhau). Đồng thời sao chép phòng vệ trong constructor và accessor; nếu không, nội dung mảng có thể đổi sau khi đã làm khóa.

## 7. Một số kiểu có equality cần chú ý

Không phải kiểu component nào cũng dùng cách so sánh mà người đọc thường kỳ vọng:

| Kiểu component | Ngữ nghĩa cần lưu ý | Câu hỏi trước khi dùng làm key |
| --- | --- | --- |
| `String` | So sánh nội dung, immutable | Có cần chuẩn hóa hoa/thường hoặc khoảng trắng không? |
| `List` | So sánh phần tử theo thứ tự | Thứ tự có phải một phần của khóa không? |
| `Set` | So sánh thành viên, không phụ thuộc thứ tự duyệt | Các phần tử có equality/hash ổn định không? |
| `Map` | So sánh các ánh xạ khóa/giá trị | Cả khóa và giá trị bên trong có ổn định không? |
| `BigDecimal` | `equals` xét cả giá trị và scale | `1.0` và `1.00` có phải cùng khóa theo nghiệp vụ không? |
| Mảng | Mặc định so sánh identity | Cần identity hay equality theo nội dung? |
| Class mutable tự viết | Theo implementation `equals`/`hashCode` của class | Trường nào tham gia equality có thể thay đổi không? |
| Record lồng nhau | Theo lớp record và các component bên trong | Component lồng nhau có thật sự ổn định không? |

Ví dụ với `BigDecimal`:

```java
import java.math.BigDecimal;

record AmountKey(BigDecimal amount) {}

System.out.println(
    new AmountKey(new BigDecimal("1.0"))
        .equals(new AmountKey(new BigDecimal("1.00")))
); // false
```

Nếu nghiệp vụ coi hai giá trị tiền tệ có cùng giá trị số là một khóa, hãy chuẩn hóa scale theo quy tắc tiền tệ trước khi lưu vào record. Đừng tự giả định `BigDecimal.equals` tương đương `compareTo`.

## 8. Ngoại lệ: collection dùng comparator hoặc identity

Không phải mọi `Map`/`Set` đều dùng `equals` của record để xác định phần tử trùng:

| Collection | Tiêu chí khóa/phần tử tương đương |
| --- | --- |
| `HashMap`, `HashSet` | `hashCode` kết hợp `equals` |
| `LinkedHashMap`, `LinkedHashSet` | Cùng equality semantics với collection hash tương ứng |
| `TreeMap`, `TreeSet` | Comparator hoặc `compareTo` trả về `0` |
| `IdentityHashMap` | Cùng tham chiếu theo `==` |

Với `TreeMap`/`TreeSet`, nếu comparator xem hai record là tương đương (trả về `0`) thì collection coi chúng là cùng khóa/phần tử, kể cả khi `equals` trả về `false`. Nên thiết kế comparator nhất quán với `equals` khi muốn giữ đúng hợp đồng thông thường của `Set`/`Map`.

`IdentityHashMap` là collection chuyên biệt: hai instance record khác nhau được giữ thành hai khóa ngay cả khi `equals` trả về `true`. Chỉ dùng khi thuật toán thực sự cần theo dõi identity của từng object, chẳng hạn trong xử lý object graph hoặc metadata gắn với từng instance.

## 9. Map không thể làm component mutable trở nên bất biến

Ngay cả khi dùng một map không thể sửa, khóa record bên trong vẫn phải có equality/hash ổn định. Tương tự, một map được bọc bằng `Collections.unmodifiableMap` chỉ chặn thao tác sửa qua wrapper; nó không đóng băng object làm khóa.

Hãy phân biệt hai cấp độ:

- **Collection bất biến về cấu trúc:** không thêm/xóa/thay thế phần tử qua API collection.
- **Khóa bất biến theo equality:** dữ liệu mà `equals`/`hashCode` sử dụng không thay đổi trong thời gian được lưu làm khóa.

Một `Map` không thể sửa có thể chứa khóa mutable; một record có trường `final` có thể chứa `List` mutable. Hai điều đó không tự bảo đảm khóa an toàn.

## 10. Checklist trước khi dùng record làm key hoặc Set element

1. Các component có thể hiện đúng ý nghĩa nghiệp vụ của khóa/phần tử không?
2. Hai instance cùng dữ liệu có nên được xem là một khóa hay một phần tử không?
3. `equals` và `hashCode` của mọi component có tuân thủ hợp đồng và ổn định không?
4. Có component mutable như `List`, `Map` hoặc class tự viết không?
5. Đã snapshot collection bằng `List.copyOf`/`Set.copyOf`/`Map.copyOf` chưa? Phần tử bên trong có cần sao chép sâu không?
6. Có array component cần so sánh theo nội dung không?
7. Có kiểu như `BigDecimal` cần chuẩn hóa theo quy tắc nghiệp vụ không?
8. Collection đang dùng equality, comparator hay identity?
9. Có thay đổi dữ liệu tham gia equality trong lúc khóa/phần tử đang được lưu không?
10. Có đang dùng `hashCode` hoặc `toString` như một định danh bền vững không? Nếu có, hãy dùng khóa nghiệp vụ hoặc ID riêng.

**Ghi nhớ:** Record là lựa chọn tốt cho key trong `Map` và phần tử trong `Set` khi equality phản ánh đúng nghiệp vụ, `equals`/`hashCode` của mọi component nhất quán, và trạng thái tham gia hai phương thức không thay đổi trong thời gian lưu trữ. Hãy ưu tiên component bất biến, snapshot dữ liệu collection và chọn đúng semantics cho mảng, số thập phân, comparator hoặc identity-based collection.

## Tài liệu chính thức

- [Java SE 26 API — `java.lang.Record`, hợp đồng `equals`, `hashCode` và copy invariant](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Record.html).
- [Java SE 26 API — `java.util.Map`, hợp đồng khóa và tra cứu](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html).
- [Java SE 26 API — `java.util.Set`, hợp đồng phần tử duy nhất](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Set.html).
- [Java SE 26 API — `java.util.List.copyOf`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).
- [Java Language Specification, Section 8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.10).
- [JEP 395 — Records, tính năng chính thức trong Java 16](https://openjdk.org/jeps/395).
