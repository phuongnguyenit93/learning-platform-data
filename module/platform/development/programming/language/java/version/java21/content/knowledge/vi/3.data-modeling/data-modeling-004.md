# Phân biệt record bất biến nông với dữ liệu thực sự bất biến

## Mục tiêu

Trong Java 21, `record` là cách gọn để khai báo một kiểu dữ liệu mang các thành phần và cung cấp ngữ nghĩa giá trị. Các thành phần của record được lưu trong những field `final`, nhưng điều đó không có nghĩa mọi đối tượng mà record tham chiếu đến đều bất biến. Một record chứa `List`, `Map`, mảng hoặc một đối tượng có thể thay đổi vẫn có thể quan sát trạng thái khác sau khi được tạo.

Bài học này phân biệt tính bất biến nông của record với tính bất biến thực sự của toàn bộ dữ liệu, đồng thời trình bày cách thiết kế constructor, accessor và cấu trúc dữ liệu để tránh rò rỉ tham chiếu có thể thay đổi.

## 1. Record bảo đảm điều gì?

Ví dụ một record đơn giản:

```java
public record Customer(String id, String name) {
}
```

Khi khai báo record, Java tự cung cấp các thành phần chính:

- Một field `private final` cho mỗi component (`id` và `name`).
- Constructor chuẩn (canonical constructor) để khởi tạo các component.
- Accessor cùng tên component, chẳng hạn `id()` và `name()`.
- Các triển khai `equals()`, `hashCode()` và `toString()` dựa trên component.
- Bản thân kiểu record là `final`, vì vậy không thể tạo lớp con từ record đó.

Sau khi khởi tạo, không thể gán lại field component của record. Với ví dụ trên, `String` cũng là kiểu bất biến, nên `Customer` không để lộ trạng thái có thể thay đổi thông qua hai component này.

Tuy nhiên, `final` chỉ cố định giá trị tham chiếu được lưu trong field. Nó không khóa đối tượng nằm ở phía sau tham chiếu. Nếu component là một đối tượng mutable, đối tượng đó vẫn có thể thay đổi trạng thái.

## 2. Vì sao record có thể chỉ bất biến nông?

Xét record chứa danh sách:

```java
import java.util.List;

record Team(String name, List<String> members) {
}
```

Record này không tự sao chép hoặc khóa danh sách. Đoạn mã sau minh họa hai đường thay đổi trạng thái:

```java
import java.util.ArrayList;
import java.util.List;

public class ShallowRecordDemo {
    public static void main(String[] args) {
        var source = new ArrayList<>(List.of("An", "Binh"));
        var team = new Team("Platform", source);

        source.add("Chi");
        System.out.println(team.members()); // [An, Binh, Chi]

        team.members().add("Dung");
        System.out.println(team.members()); // [An, Binh, Chi, Dung]
    }
}
```

Hai thao tác trên đều làm thay đổi dữ liệu mà `team` quan sát được:

1. Mã bên ngoài giữ `source`, tức là vẫn giữ tham chiếu đến đúng danh sách được truyền vào constructor.
2. Accessor `members()` trả về tham chiếu đến danh sách nội bộ, nên bên gọi có thể sửa danh sách đó.

Các field của `Team` vẫn là `final`; tham chiếu `members` không bị gán lại. Nhưng trạng thái của đối tượng `List` mà field trỏ tới đã thay đổi. Đây là **bất biến nông (shallow immutability)**: lớp hoặc record giữ cố định các tham chiếu của mình, trong khi các đối tượng được tham chiếu vẫn có thể thay đổi.

**Bất biến thực sự ở cấp dữ liệu (deep immutability)** đòi hỏi trạng thái có thể quan sát của toàn bộ đồ thị đối tượng mà dữ liệu sở hữu không thể bị thay đổi sau khi tạo. Muốn đạt điều đó, các thành phần cần là kiểu bất biến hoặc phải được bảo vệ bằng sao chép phòng vệ phù hợp ở mọi ranh giới truy cập.

## 3. Bắt đầu từ các kiểu dữ liệu bất biến

Thiết kế dễ kiểm soát nhất là dùng các component vốn đã bất biến. Những kiểu thường phù hợp gồm:

- Các kiểu nguyên thủy như `int`, `long`, `boolean`.
- Các wrapper như `Integer`, `Long`, `Boolean`.
- `String` và các kiểu enum.
- `BigInteger`, `BigDecimal`.
- Các kiểu ngày giờ hiện đại trong `java.time`, chẳng hạn `LocalDate`, `Instant` và `LocalDateTime`.
- Các record khác nếu chính những component bên trong chúng cũng bất biến.

Ví dụ, các record sau tạo thành một cấu trúc dữ liệu chỉ chứa những giá trị bất biến:

```java
import java.math.BigDecimal;
import java.util.Objects;

record Price(BigDecimal amount, String currencyCode) {
    Price {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currencyCode, "currencyCode");

        if (amount.signum() < 0) {
            throw new IllegalArgumentException("amount must not be negative");
        }
        if (currencyCode.isBlank()) {
            throw new IllegalArgumentException("currencyCode must not be blank");
        }
    }
}

record Product(String sku, String name, Price price) {
    Product {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(name, "name");
        Objects.requireNonNull(price, "price");
    }
}
```

`Price` kiểm tra dữ liệu đầu vào trong compact canonical constructor. `BigDecimal` và `String` không cho phép thay đổi trạng thái của giá trị hiện có. `Product` tham chiếu đến `Price`, một record cũng chỉ chứa các giá trị bất biến. Vì vậy, người dùng không thể thay đổi giá của một `Product` thông qua các accessor của nó.

Điểm quan trọng là phải xem xét đệ quy từng component. Một record chứa một record khác không tự động trở nên bất biến nếu record lồng bên trong lại chứa danh sách hoặc đối tượng mutable.

## 4. Bảo vệ collection bằng bản sao không thể sửa đổi

Java cung cấp các factory method như `List.copyOf`, `Set.copyOf` và `Map.copyOf`. Chúng tạo ra collection không thể sửa đổi thông qua API collection thông thường. Với record, có thể chuẩn hóa và sao chép đầu vào ngay trong compact canonical constructor.

```java
import java.util.List;
import java.util.Objects;

record Team(String name, List<String> members) {
    public Team {
        Objects.requireNonNull(name, "name");
        members = List.copyOf(members);
    }
}
```

Giờ đây, `Team` không giữ tham chiếu đến danh sách mutable mà bên gọi truyền vào. Ví dụ:

```java
import java.util.ArrayList;
import java.util.List;

public class TeamCopyDemo {
    public static void main(String[] args) {
        var source = new ArrayList<>(List.of("An", "Binh"));
        var team = new Team("Platform", source);

        source.add("Chi");
        System.out.println(team.members()); // [An, Binh]

        team.members().add("Dung"); // ném UnsupportedOperationException
    }
}
```

`List.copyOf` tạo một snapshot không thể sửa đổi của cấu trúc danh sách đầu vào. Việc thêm hoặc xóa phần tử trong danh sách nguồn sau đó không làm thay đổi cấu trúc danh sách được record giữ. Các factory method tương ứng có thể áp dụng cho `Set` và `Map`:

```java
import java.util.Map;
import java.util.Set;

record Permissions(Set<String> values) {
    public Permissions {
        values = Set.copyOf(values);
    }
}

record Configuration(Map<String, String> values) {
    public Configuration {
        values = Map.copyOf(values);
    }
}
```

Các phương thức `copyOf` từ chối collection đầu vào là `null`; chúng cũng từ chối phần tử `null` đối với `List` và `Set`, và từ chối khóa hoặc giá trị `null` đối với `Map`. Nếu mô hình dữ liệu cho phép `null`, cần xác định rõ quy tắc đó và chọn cách biểu diễn phù hợp thay vì vô tình dựa vào các factory method này.

### Collection không thể sửa đổi không đồng nghĩa với phần tử bất biến

`List.copyOf` chỉ bảo vệ cấu trúc collection. Đây là phép sao chép nông: các phần tử vẫn là những đối tượng được tham chiếu từ danh sách ban đầu. Nếu phần tử có thể thay đổi, người giữ tham chiếu đến phần tử đó vẫn có thể thay đổi trạng thái mà record quan sát được.

Ví dụ:

```java
import java.util.List;

final class MutableMember {
    private String name;

    MutableMember(String name) {
        this.name = name;
    }

    void rename(String newName) {
        this.name = newName;
    }

    String name() {
        return name;
    }
}

record Group(List<MutableMember> members) {
    public Group {
        members = List.copyOf(members);
    }
}
```

Danh sách bên trong `Group` không thể thêm hoặc xóa phần tử, nhưng đối tượng `MutableMember` vẫn có thể đổi tên. Vì vậy, `List.copyOf` chưa đủ để làm `Group` bất biến sâu.

Ưu tiên chuyển phần tử thành kiểu bất biến nếu có thể:

```java
import java.util.List;

record Member(String name) {
}

record Group(List<Member> members) {
    public Group {
        members = List.copyOf(members);
    }
}
```

Với `Member` chỉ chứa `String`, danh sách không thể sửa đổi và các phần tử cũng bất biến. Khi đó, cấu trúc dữ liệu không còn đường thay đổi trạng thái thông qua các tham chiếu được công khai.

### Phân biệt snapshot với unmodifiable view

`Collections.unmodifiableList(source)` tạo một view không cho phép sửa danh sách thông qua view đó, nhưng view vẫn dựa trên danh sách nguồn. Nếu mã khác sửa `source`, người đọc view sẽ thấy thay đổi đó.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class CollectionViewDemo {
    public static void main(String[] args) {
        var source = new ArrayList<>(List.of("A"));
        var view = Collections.unmodifiableList(source);
        var snapshot = List.copyOf(source);

        source.add("B");

        System.out.println(view);     // [A, B]
        System.out.println(snapshot); // [A]
    }
}
```

Khi cần lưu trạng thái độc lập với collection mutable do bên gọi sở hữu, `copyOf` thường phù hợp hơn unmodifiable view. Dù chọn cách nào, vẫn cần xem xét khả năng thay đổi của từng phần tử.

## 5. Bảo vệ mảng và đối tượng mutable

Mảng trong Java luôn có thể thay đổi phần tử. Một record nhận mảng và trả mảng trực tiếp sẽ để lộ trạng thái nội bộ:

```java
record Digest(byte[] bytes) {
}
```

Để bảo vệ mảng, cần sao chép khi nhận đầu vào và sao chép một lần nữa khi trả dữ liệu ra ngoài:

```java
import java.util.Objects;

public record Digest(byte[] bytes) {
    public Digest {
        bytes = Objects.requireNonNull(bytes, "bytes").clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }
}
```

- `clone()` trong constructor ngăn bên gọi sửa mảng nguồn để tác động đến record.
- Accessor được override để mỗi lần đọc đều nhận một bản sao, không nhận mảng nội bộ.
- Mã gọi có thể sửa bản sao nhận được mà không ảnh hưởng đến `Digest`.

Đối với một lớp mutable khác, nguyên tắc tương tự: sao chép đối tượng đầu vào trước khi lưu và không trả tham chiếu trực tiếp đến đối tượng nội bộ. Bản sao phải đủ sâu để không còn dùng chung các đối tượng mutable lồng bên trong. Nếu kiểu đó không cung cấp cơ chế sao chép đáng tin cậy, hãy thiết kế một kiểu giá trị bất biến riêng hoặc chuyển đổi dữ liệu sang biểu diễn bất biến.

### Lưu ý về `equals()` và `hashCode()` với mảng

Các phương thức `equals()` và `hashCode()` do record sinh ra dựa trên cách so sánh component. Với component là mảng, phép so sánh thông thường của mảng không so sánh nội dung từng phần tử như `Arrays.equals`; hai mảng khác nhau nhưng có nội dung giống nhau vẫn không được xem là bằng nhau theo cách so sánh tham chiếu mặc định.

Nếu record có mảng cần ngữ nghĩa giá trị theo nội dung, hãy cân nhắc một kiểu biểu diễn khác hoặc chủ động triển khai `equals()` và `hashCode()` phù hợp, chẳng hạn dùng `Arrays.equals()` và `Arrays.hashCode()`. Việc sao chép phòng vệ bảo vệ tính bất biến, nhưng tự nó không thay đổi ngữ nghĩa so sánh của mảng.

## 6. Quy tắc thiết kế record chứa dữ liệu phức hợp

Khi một record có component tham chiếu đến dữ liệu có thể thay đổi, hãy xem xét hai chiều rò rỉ tham chiếu:

1. **Đầu vào (defensive copy on ingress):** bên gọi còn giữ tham chiếu đến đối tượng được truyền vào hay không? Nếu có, cần tạo bản sao hoặc chuyển đổi sang kiểu bất biến trước khi lưu.
2. **Đầu ra (defensive copy on egress):** accessor có trả về tham chiếu trực tiếp đến trạng thái mutable bên trong hay không? Nếu có, cần trả bản sao hoặc một biểu diễn không thể sửa đổi và không bị ảnh hưởng bởi nguồn mutable bên ngoài.

Có thể áp dụng các nguyên tắc sau:

- Ưu tiên component là kiểu nguyên thủy, `String`, enum hoặc kiểu giá trị bất biến.
- Dùng compact canonical constructor để kiểm tra `null`, xác thực điều kiện và chuẩn hóa dữ liệu đầu vào.
- Với collection, dùng `List.copyOf`, `Set.copyOf` hoặc `Map.copyOf` khi hợp đồng dữ liệu phù hợp; đồng thời bảo đảm các phần tử, khóa và giá trị cũng bất biến.
- Với mảng, sao chép trong constructor và override accessor để trả bản sao.
- Với đối tượng mutable tùy chỉnh, xác định rõ quy tắc sao chép sâu và tránh để lộ tham chiếu đến trạng thái nội bộ.
- Kiểm tra cả những component lồng nhau. Một record chỉ thực sự bất biến sâu khi toàn bộ dữ liệu có thể thay đổi mà nó sở hữu đều được bảo vệ.

## 7. Ví dụ tổng hợp: danh mục sản phẩm bất biến

Có thể kết hợp record, kiểu giá trị bất biến và bản sao collection để xây dựng một mô hình dữ liệu có thể chia sẻ an toàn qua nhiều phần của ứng dụng:

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

record Price(BigDecimal amount, String currencyCode) {
    Price {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currencyCode, "currencyCode");
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("amount must not be negative");
        }
    }
}

record Product(String sku, String name, Price price) {
    Product {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(name, "name");
        Objects.requireNonNull(price, "price");
    }
}

record Catalog(List<Product> products) {
    Catalog {
        products = List.copyOf(products);
    }
}

public class CatalogExample {
    public static void main(String[] args) {
        var products = List.of(
                new Product("KB-01", "Keyboard",
                        new Price(new BigDecimal("49.90"), "USD")),
                new Product("MS-02", "Mouse",
                        new Price(new BigDecimal("19.50"), "USD"))
        );

        var catalog = new Catalog(products);
        System.out.println(catalog.products());
    }
}
```

Trong mô hình này:

- `Price` chứa `BigDecimal` và `String`, đều là kiểu bất biến.
- `Product` chứa `String` và một `Price` bất biến.
- `Catalog` giữ một danh sách không thể sửa đổi được tạo bằng `List.copyOf`.
- Các phần tử trong danh sách cũng bất biến, nên không thể sửa sản phẩm thông qua tham chiếu lấy từ accessor.

Do đó, toàn bộ cấu trúc dữ liệu được tạo thành từ các giá trị bất biến và collection không thể sửa đổi. Nếu mô hình sau này thêm một component mutable, cần đánh giá lại các quy tắc sao chép và accessor thay vì giả định `record` đã giải quyết tính bất biến.

## 8. Cách tự kiểm tra tính bất biến

Khi review một record, hãy thử trả lời các câu hỏi sau:

1. Có thể thay đổi trạng thái record thông qua một tham chiếu đầu vào mà bên gọi vẫn giữ không?
2. Accessor có trả về một collection, mảng hoặc đối tượng mutable nội bộ không?
3. Collection đã được sao chép chưa, và các phần tử bên trong có bất biến không?
4. Đối tượng mutable lồng nhau có được sao chép sâu hoặc chuyển đổi sang kiểu bất biến không?
5. Các quy tắc `equals()` và `hashCode()` có phù hợp với cách biểu diễn component, đặc biệt khi có mảng không?

Một phép thử thực tế hữu ích là tạo record từ dữ liệu nguồn mutable, sau đó sửa dữ liệu nguồn và thử sửa dữ liệu đọc qua accessor. Nếu trạng thái mà record công khai thay đổi ngoài dự kiến, cấu trúc dữ liệu vẫn còn đường rò rỉ tham chiếu mutable.

## Kết luận

Record trong Java 21 cố định các field component sau khi khởi tạo, nhưng chỉ cung cấp tính bất biến nông khi component tham chiếu đến đối tượng mutable. Để tạo dữ liệu thực sự bất biến, hãy ưu tiên các kiểu giá trị bất biến, sao chép collection và mảng ở ranh giới constructor/accessor, đồng thời kiểm tra toàn bộ các phần tử và đối tượng lồng nhau. Tính bất biến đến từ thiết kế của toàn bộ đồ thị dữ liệu, không chỉ từ từ khóa `record` hoặc `final`.
