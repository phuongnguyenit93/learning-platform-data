# Phần tử mutable vẫn có thể thay đổi bên trong danh sách unmodifiable

`Stream.toList()` trả về một `List` không sửa đổi được (*unmodifiable list*), nhưng điều đó chỉ bảo vệ cấu trúc của danh sách. Nếu phần tử là object mutable, trạng thái bên trong object vẫn có thể thay đổi thông qua tham chiếu lấy từ danh sách hoặc một tham chiếu khác đang trỏ tới cùng object.

Vì vậy, cần phân biệt hai việc: thay đổi danh sách, chẳng hạn thêm hoặc thay phần tử, và thay đổi object đang được danh sách tham chiếu. `toList()` ngăn việc thứ nhất; nó không tự thực hiện deep copy hoặc biến các phần tử thành immutable.

## 1. Danh sách không sửa đổi được không làm phần tử bất biến

Ví dụ đơn giản với `StringBuilder`:

```java
import java.util.List;
import java.util.stream.Stream;

StringBuilder message = new StringBuilder("Xin chào");
List<StringBuilder> messages = Stream.of(message).toList();

messages.get(0).append(" Java");
System.out.println(messages.get(0)); // Xin chào Java

messages.add(new StringBuilder("Khác")); // UnsupportedOperationException
```

Lời gọi `append()` thay đổi object `StringBuilder` mà phần tử số 0 đang tham chiếu tới. Danh sách vẫn chứa đúng một phần tử, ở đúng vị trí cũ. Ngược lại, `add()` cố thay đổi cấu trúc danh sách nên bị từ chối.

Có thể hiểu đây là tính không sửa đổi ở mức cấu trúc (*shallow unmodifiable*): danh sách không cho phép thay đổi các tham chiếu phần tử được lưu trong nó, nhưng không kiểm soát mọi trạng thái có thể truy cập từ các tham chiếu ấy.

## 2. Thay đổi qua tham chiếu bên ngoài (aliasing)

Một object có thể được tham chiếu từ nhiều biến. `toList()` không tự nhân bản object khi thu thập stream; nếu pipeline phát ra một tham chiếu tới object, danh sách kết quả giữ phần tử đó. Các đoạn mã dùng cùng tham chiếu sẽ quan sát được trạng thái đã sửa trong cùng luồng thực thi; giữa nhiều luồng còn phải bảo đảm visibility và đồng bộ hóa phù hợp.

```java
import java.util.List;
import java.util.stream.Stream;

StringBuilder status = new StringBuilder("Pending");

List<StringBuilder> result = Stream.of(status).toList();
status.replace(0, status.length(), "Completed");

System.out.println(result.get(0)); // Completed
```

Thay đổi được thực hiện qua biến `status`, nhưng có thể quan sát qua `result.get(0)` vì cả hai cùng trỏ tới một object.

Điều ngược lại cũng đúng: nếu lấy phần tử từ danh sách rồi sửa object, biến bên ngoài cũng nhìn thấy thay đổi:

```java
result.get(0).append("!");
System.out.println(status); // Completed!
```

Đây là hành vi bình thường của mô hình tham chiếu trong Java. Tính unmodifiable của collection không thay đổi quy tắc aliasing này.

## 3. Mảng và collection lồng nhau cũng có thể mutable

Phần tử không nhất thiết phải là một class có setter. Mảng và collection đều có thể thay đổi trạng thái sau khi được đưa vào danh sách.

**Mảng:**

```java
import java.util.List;
import java.util.stream.Stream;

byte[] payload = { 10, 20, 30 };
List<byte[]> packets = Stream.of(payload).toList();

packets.get(0)[1] = 99; // Hợp lệ: sửa nội dung mảng
System.out.println(packets.get(0)[1]); // 99

packets.set(0, new byte[] { 1, 2 }); // UnsupportedOperationException
```

Danh sách không cho thay mảng được lưu tại vị trí 0, nhưng không ngăn ghi vào một ô của chính mảng đó.

**Collection lồng nhau:**

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

List<String> tags = new ArrayList<>(List.of("java", "stream"));
List<List<String>> groups = Stream.of(tags).toList();

groups.get(0).add("java16"); // Hợp lệ: List bên trong mutable
System.out.println(groups); // [[java, stream, java16]]

groups.add(new ArrayList<>()); // UnsupportedOperationException
```

Ở đây có hai lớp cấu trúc: danh sách ngoài không sửa đổi được, còn `tags` là `ArrayList` mutable. Nếu phần tử của collection ngoài là một collection khác, phải xác định riêng hợp đồng của từng lớp lồng nhau.

## 4. Record cũng chỉ bất biến nông

Record rất hữu ích để biểu diễn dữ liệu, nhưng các component của record không tự được deep copy. Trường được sinh ra là `final`, nghĩa là không thể gán lại tham chiếu component sau khi khởi tạo; object mà tham chiếu đó trỏ tới vẫn có thể mutable.

Ví dụ, record sau chứa một `List` mutable:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

record Team(String name, List<String> members) {}

List<String> members = new ArrayList<>(List.of("An", "Bình"));
Team team = new Team("Platform", members);
List<Team> teams = Stream.of(team).toList();

teams.get(0).members().add("Chi"); // Hợp lệ
System.out.println(teams.get(0).members()); // [An, Bình, Chi]

teams.set(0, new Team("Other", List.of())); // UnsupportedOperationException
```

`teams` không cho thay record ở vị trí 0. Tuy nhiên, accessor `members()` trả về chính tham chiếu tới danh sách mutable được truyền vào constructor, nên người gọi có thể sửa danh sách component.

### Bảo vệ component collection bằng defensive copy

Nếu component chỉ cần chứa các giá trị immutable như `String`, record có thể sao chép collection đầu vào thành một danh sách không sửa đổi được trong compact constructor:

```java
import java.util.List;

record Team(String name, List<String> members) {
    Team {
        members = List.copyOf(members);
    }
}
```

`List.copyOf()` trả về một danh sách không sửa đổi được và từ chối phần tử `null`; implementation có thể tái sử dụng một danh sách đã không sửa đổi được. Vì `String` là immutable, ví dụ này bảo vệ cả cấu trúc component lẫn các giá trị tên thành viên. Nếu component chứa object mutable, `List.copyOf()` chỉ bảo vệ cấu trúc danh sách; các object bên trong vẫn cần được sao chép hoặc thiết kế immutable riêng.

## 5. Phân biệt sao chép nông và sao chép sâu

Khi cần tách kết quả khỏi dữ liệu nguồn, hãy xác định cần sao chép đến mức nào:

| Cách làm | Cấu trúc danh sách mới | Object phần tử | Khi phù hợp |
| --- | --- | --- | --- |
| `stream.toList()` | Kết quả không sửa đổi được | Giữ các object mà stream phát ra; không deep copy | Khi cần kết quả danh sách để đọc. |
| `new ArrayList<>(result)` | Mutable và độc lập về cấu trúc | Vẫn dùng các tham chiếu phần tử cũ | Khi chỉ cần thêm, xóa hoặc sắp xếp danh sách. |
| `List.copyOf(result)` | Không sửa đổi được | Vẫn dùng các tham chiếu phần tử cũ | Khi cần một cấu trúc danh sách không sửa đổi được từ collection đầu vào. |
| Sao chép từng phần tử | Tùy collection được tạo | Tạo object khác theo logic sao chép | Khi cần tách trạng thái mutable của phần tử khỏi nguồn. |

Ví dụ, tạo snapshot chỉ chứa giá trị immutable thay vì chia sẻ object mutable:

```java
import java.math.BigDecimal;
import java.util.List;

class MutableProduct {
    private final String code;
    private BigDecimal price;

    MutableProduct(String code, BigDecimal price) {
        this.code = code;
        this.price = price;
    }

    String code() { return code; }
    BigDecimal price() { return price; }
    void changePrice(BigDecimal newPrice) { price = newPrice; }
}

record ProductSnapshot(String code, BigDecimal price) {}

class SnapshotExample {
    static List<ProductSnapshot> snapshots(List<MutableProduct> products) {
        return products.stream()
            .map(product -> new ProductSnapshot(product.code(), product.price()))
            .toList();
    }
}
```

`ProductSnapshot` chỉ giữ `String` và `BigDecimal`, đều là kiểu immutable. Danh sách kết quả không sửa đổi được, và snapshot không chia sẻ object `MutableProduct` với nguồn. Nếu dùng một kiểu phần tử mutable khác, cần viết logic sao chép phù hợp thay vì chỉ sao chép collection.

## 6. Tạo kết quả có cấu trúc lồng nhau không sửa đổi được

Nếu dữ liệu gồm nhiều danh sách con và các phần tử là immutable, có thể bảo vệ từng cấp bằng cách sao chép mỗi danh sách con trước, rồi thu danh sách ngoài bằng `toList()`:

```java
import java.util.List;
import java.util.Map;

Map<String, List<String>> source = Map.of(
    "backend", List.of("Java", "SQL"),
    "frontend", List.of("HTML", "CSS")
);

List<List<String>> groupedValues = source.values().stream()
    .map(List::copyOf)
    .toList();
```

Trong ví dụ này, các giá trị phần tử là `String` immutable, danh sách con từ `List.copyOf()` không sửa đổi được và danh sách ngoài từ `toList()` cũng không sửa đổi được. Nếu các phần tử con là object mutable, phải sao chép hoặc chuyển đổi chúng thành giá trị immutable ở bước `map`.

Với mảng, cần clone nội dung nếu muốn tách mảng khỏi nguồn:

```java
import java.util.List;

List<byte[]> sourcePackets = List.of(
    new byte[] { 1, 2, 3 },
    new byte[] { 4, 5, 6 }
);

List<byte[]> copiedPackets = sourcePackets.stream()
    .map(packet -> packet.clone())
    .toList();
```

`clone()` ở đây tạo mảng `byte[]` mới và sao chép các giá trị byte. Nếu mảng chứa tham chiếu tới object mutable, clone mảng vẫn chỉ là sao chép nông các phần tử bên trong.

## 7. Rủi ro khi chia sẻ danh sách giữa nhiều luồng

Một danh sách unmodifiable không tự động làm cho các object bên trong thread-safe. Nếu nhiều luồng cùng truy cập một phần tử mutable, vẫn có thể xảy ra race condition khi một luồng ghi và luồng khác đọc hoặc ghi đồng thời.

```java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;

AtomicInteger counter = new AtomicInteger(0);
List<AtomicInteger> counters = Stream.of(counter).toList();

counters.get(0).incrementAndGet(); // Hợp lệ; AtomicInteger hỗ trợ cập nhật nguyên tử
```

`AtomicInteger` được dùng ở đây vì bản thân nó cung cấp thao tác cập nhật nguyên tử. Nếu thay bằng một object mutable thông thường, cần đồng bộ hóa hoặc dùng cơ chế concurrency phù hợp cho object đó. Việc danh sách không sửa đổi được chỉ bảo vệ quan hệ phần tử của list, không thay thế thiết kế thread-safety.

## 8. Checklist khi thiết kế danh sách kết quả

- Xác định phần tử là immutable hay mutable; đừng suy ra từ việc list unmodifiable.
- Kiểm tra có tham chiếu bên ngoài nào cùng trỏ tới object phần tử không.
- Với mảng hoặc collection lồng nhau, xác định hợp đồng sửa đổi ở từng cấp.
- Record có component mutable cần defensive copy hoặc chuyển component thành kiểu immutable.
- Dùng `List.copyOf()` để bảo vệ cấu trúc component khi các phần tử phù hợp; nhớ đây là shallow copy.
- Nếu cần snapshot độc lập, tạo object phần tử mới hoặc sao chép sâu theo đúng mô hình dữ liệu.
- Khi chia sẻ giữa nhiều thread, đánh giá thread-safety của object phần tử riêng biệt.

`Stream.toList()` bảo vệ cấu trúc danh sách kết quả. Muốn dữ liệu thực sự ổn định, cần thiết kế cả object phần tử, component lồng nhau và quyền chia sẻ tham chiếu. Hãy quyết định rõ cần một danh sách không sửa đổi được, một snapshot độc lập hay một mô hình dữ liệu immutable sâu; mỗi mục tiêu cần cách xây dựng khác nhau.

## Tài liệu tham khảo

- [Stream.toList() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html#toList())
- [List.copyOf() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))
- [Record Classes – Java Language Specification](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.10)
- [AtomicInteger – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html)
