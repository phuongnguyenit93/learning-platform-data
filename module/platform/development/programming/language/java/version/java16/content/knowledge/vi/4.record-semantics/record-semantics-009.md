# Mutable component có thể làm thay đổi equals và hashCode

**Module:** `JAVA_VERSION_JAVA16`  
**Chương:** Ngữ nghĩa record  
**Áp dụng:** Java 16 trở lên, bao gồm Java hiện đại.

Record tự sinh `equals(Object)` và `hashCode()` dựa trên các record component. Các trường component là `final`, nhưng điều đó chỉ cố định **tham chiếu được lưu trong trường**. Nếu tham chiếu trỏ đến một đối tượng có thể thay đổi, trạng thái bên trong đối tượng vẫn có thể đổi sau khi record được tạo.

Khi kiểu component định nghĩa `equals` và `hashCode` dựa trên trạng thái có thể thay đổi, những thay đổi đó có thể làm kết quả so sánh và mã băm của record thay đổi theo. Đây là rủi ro quan trọng khi dùng record làm khóa `HashMap`, phần tử `HashSet` hoặc chia sẻ giữa nhiều phần của ứng dụng.

## 1. Trường `final` không có nghĩa là dữ liệu bất biến sâu

Ví dụ:

```java
import java.util.ArrayList;
import java.util.List;

record SearchCriteria(List<String> tags) {}

List<String> source = new ArrayList<>(List.of("java"));
SearchCriteria criteria = new SearchCriteria(source);

System.out.println(criteria.tags()); // [java]

source.add("records");
System.out.println(criteria.tags()); // [java, records]
```

Trường `tags` của record không thể được gán lại sau khi khởi tạo. Tuy nhiên, `tags` đang giữ tham chiếu đến một `ArrayList` có thể thay đổi. Lệnh `source.add("records")` sửa chính danh sách mà record đang tham chiếu.

Phân biệt:

- **Reference immutability:** tham chiếu trong trường không thể được gán sang một đối tượng khác.
- **Object mutability:** đối tượng mà tham chiếu trỏ đến có thể thay đổi trạng thái.
- **Deep immutability:** trạng thái của toàn bộ dữ liệu có thể truy cập qua đối tượng không thể bị thay đổi từ bên ngoài.

Record bảo đảm các trường component là `final`; nó không tự động bảo đảm deep immutability cho object graph mà component tham chiếu tới.

## 2. Vì sao `equals` của record có thể đổi theo component?

Với component kiểu tham chiếu, `equals` mặc định của record sử dụng ngữ nghĩa tương đương `Objects.equals`. Nếu component là `List`, phép so sánh dựa trên `List.equals`, tức là nội dung và thứ tự phần tử.

```java
import java.util.ArrayList;
import java.util.List;

record SearchCriteria(List<String> tags) {}

List<String> mutableTags = new ArrayList<>(List.of("java"));
SearchCriteria current = new SearchCriteria(mutableTags);
SearchCriteria expected = new SearchCriteria(List.of("java"));

System.out.println(current.equals(expected)); // true

mutableTags.add("records");
System.out.println(current.equals(expected)); // false
```

Ban đầu hai danh sách có cùng phần tử nên hai record bằng nhau. Sau khi danh sách được sửa, component của `current` có thêm phần tử, trong khi component của `expected` không đổi. Kết quả `equals` vì vậy thay đổi.

Điều này không có nghĩa mọi thay đổi bên trong mọi component đều làm đổi `equals`. Kết quả phụ thuộc hợp đồng của kiểu component:

- `List` so sánh nội dung nên thay đổi phần tử có thể làm thay đổi equality.
- Một class mutable tự triển khai `equals` dựa trên các trường có thể thay đổi cũng có thể làm equality thay đổi.
- Một class dùng identity equality như `Object` mặc định có thể giữ nguyên kết quả `equals` khi trạng thái nội bộ thay đổi, vì equality của nó không dựa trên trạng thái đó.

Vì vậy, khi đánh giá một record, hãy xem cả cách component triển khai `equals` chứ không chỉ xem component có mutable hay không.

## 3. Vì sao `hashCode` có thể đổi theo component?

`hashCode` mặc định của record được suy ra từ component. Với component tham chiếu, mã băm của component được lấy theo ngữ nghĩa `hashCode` của chính đối tượng đó. `List.hashCode` phụ thuộc vào các phần tử và thứ tự phần tử, nên thêm hoặc xóa phần tử có thể làm mã băm của record thay đổi.

```java
import java.util.ArrayList;
import java.util.List;

record SearchCriteria(List<String> tags) {}

List<String> tags = new ArrayList<>(List.of("java"));
SearchCriteria criteria = new SearchCriteria(tags);

int hashBefore = criteria.hashCode();
tags.add("records");
int hashAfter = criteria.hashCode();

System.out.println(hashBefore == hashAfter); // false với dữ liệu ví dụ này
```

Hợp đồng `Object.hashCode` yêu cầu mã băm ổn định khi thông tin được dùng trong `equals` không thay đổi. Nếu trạng thái tham gia `equals` đã thay đổi, mã băm cũng có thể thay đổi. Không có yêu cầu rằng mọi thay đổi đều phải tạo ra một mã băm khác: va chạm hoặc trùng hash vẫn có thể xảy ra.

Đối với một component dùng identity-based `equals`/`hashCode`, thay đổi nội dung có thể không làm đổi mã băm. Ví dụ mảng Java không ghi đè `Object.hashCode`; record mặc định chứa mảng dùng mã băm identity của mảng, không phải mã băm theo phần tử. Hãy phân biệt trường hợp này với `List` hoặc class có hash dựa trên trạng thái.

## 4. Bẫy khi dùng record làm khóa `HashMap` hoặc phần tử `HashSet`

Các collection hash tổ chức phần tử dựa trên mã băm tại thời điểm chèn. Khi tìm kiếm, chúng tính hash của khóa hiện tại để xác định vùng cần kiểm tra, sau đó dùng `equals` để so sánh.

Ví dụ:

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

record SearchCriteria(List<String> tags) {}

List<String> tags = new ArrayList<>(List.of("java"));
SearchCriteria key = new SearchCriteria(tags);

Set<SearchCriteria> criteriaSet = new HashSet<>();
criteriaSet.add(key);

tags.add("records"); // Thay đổi dữ liệu tham gia hashCode.

System.out.println(criteriaSet.contains(key)); // Có thể false
```

Khi chèn, `HashSet` lưu phần tử cùng mã băm lúc danh sách chỉ có `"java"`. Sau đó danh sách thay đổi, nên `key.hashCode()` được tính lại từ trạng thái mới. Nếu hash mới khác hash đã lưu, phép tra cứu có thể không tìm thấy entry cũ, kể cả khi truyền lại đúng cùng instance `key`.

Entry chưa chắc đã biến mất khỏi collection: duyệt collection vẫn có thể thấy đối tượng. Vấn đề là vị trí nội bộ được tổ chức theo trạng thái hash cũ, trong khi thao tác tra cứu dùng trạng thái hash mới. `HashMap` có thể gặp cùng vấn đề khi khóa chứa component mutable.

Quy tắc thực hành: **không thay đổi thông tin tham gia `equals`/`hashCode` của một khóa trong thời gian khóa đó đang nằm trong hash collection**.

## 5. Sao chép phòng vệ với `List.copyOf`

Với component là danh sách chứa các phần tử bất biến như `String`, có thể tạo snapshot cấu trúc trong compact constructor:

```java
import java.util.List;

record SearchCriteria(List<String> tags) {
    SearchCriteria {
        tags = List.copyOf(tags);
    }
}
```

`List.copyOf` tạo một danh sách không thể sửa qua API `List` và không phản ánh những thay đổi cấu trúc xảy ra sau đó trên collection đầu vào. Ví dụ:

```java
import java.util.ArrayList;
import java.util.List;

record SearchCriteria(List<String> tags) {
    SearchCriteria {
        tags = List.copyOf(tags);
    }
}

List<String> source = new ArrayList<>(List.of("java"));
SearchCriteria criteria = new SearchCriteria(source);

source.add("records");
System.out.println(criteria.tags()); // [java]

// criteria.tags().add("streams"); // UnsupportedOperationException
```

Accessor mặc định trả về chính danh sách không thể sửa đó, nên bên gọi không thể thêm hoặc xóa phần tử qua accessor. Cách này phù hợp vì `String` là immutable.

Lưu ý:

- `List.copyOf` không cho phép phần tử `null`; đầu vào có `null` sẽ gây `NullPointerException`.
- Đây là bản sao nông (*shallow copy*) về cấu trúc collection.
- Nếu phần tử là object mutable, trạng thái của phần tử vẫn có thể thay đổi.
- `Set.copyOf` và `Map.copyOf` cũng tạo collection không thể sửa, nhưng không tự sao chép sâu các phần tử hoặc khóa/giá trị.

Đừng nhầm snapshot với một view không thể sửa. `Collections.unmodifiableList(source)` chỉ chặn thao tác sửa thông qua wrapper; nếu mã khác vẫn giữ `source` và thay đổi danh sách gốc, wrapper sẽ phản ánh thay đổi đó. Muốn snapshot, hãy sao chép dữ liệu trước hoặc dùng `List.copyOf`.

## 6. Bản sao nông không bảo vệ phần tử mutable

Ví dụ sau vẫn có thể thay đổi kết quả equality dù danh sách đã được sao chép và không thể thêm/xóa phần tử:

```java
import java.util.List;
import java.util.Objects;

final class MutableTag {
    private String name;

    MutableTag(String name) {
        this.name = Objects.requireNonNull(name);
    }

    String name() {
        return name;
    }

    void rename(String newName) {
        name = Objects.requireNonNull(newName);
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof MutableTag that
            && name.equals(that.name);
    }

    @Override
    public int hashCode() {
        return name.hashCode();
    }
}

record TaggedItems(List<MutableTag> tags) {
    TaggedItems {
        tags = List.copyOf(tags);
    }
}

MutableTag tag = new MutableTag("java");
TaggedItems items = new TaggedItems(List.of(tag));
TaggedItems expected =
    new TaggedItems(List.of(new MutableTag("java")));

System.out.println(items.equals(expected)); // true

tag.rename("records");
System.out.println(items.equals(expected)); // false
```

`List.copyOf` đã ngăn thay đổi cấu trúc danh sách, nhưng hai danh sách vẫn chứa tham chiếu đến các đối tượng `MutableTag`. Khi `tag.rename` thay đổi trường `name`, `MutableTag.equals` và `MutableTag.hashCode` thay đổi theo; record chứa danh sách cũng bị ảnh hưởng.

## 7. Sao chép sâu hoặc chuyển sang component bất biến

Khi component chứa object mutable, có hai hướng phổ biến:

1. Chuyển dữ liệu sang kiểu bất biến đại diện cho giá trị cần lưu.
2. Tạo bản sao sâu theo đúng cấu trúc miền dữ liệu, cả lúc nhận đầu vào lẫn lúc trả dữ liệu ra.

Ví dụ sau tiếp tục dùng lớp `MutableTag` ở mục trước và chuyển tag mutable thành record chỉ chứa `String`:

```java
import java.util.ArrayList;
import java.util.List;

record Tag(String name) {}
record TaggedItems(List<Tag> tags) {
    TaggedItems {
        tags = List.copyOf(tags);
    }
}

List<MutableTag> mutableTags =
    new ArrayList<>(List.of(new MutableTag("java")));

List<Tag> snapshot = mutableTags.stream()
    .map(tag -> new Tag(tag.name()))
    .toList();

TaggedItems items = new TaggedItems(snapshot);
mutableTags.get(0).rename("records");

System.out.println(items.tags()); // [Tag[name=java]]
```

`Tag` là record chứa `String`, nên trạng thái dữ liệu được snapshot không bị ảnh hưởng khi object `MutableTag` ban đầu thay đổi. `Stream.toList()` có từ Java 16 và trả về danh sách không thể sửa; constructor vẫn dùng `List.copyOf` để thể hiện rõ hợp đồng của record.

Nếu cần giữ kiểu mutable ban đầu, hãy viết hàm sao chép sâu cho từng loại object. Không có một thao tác clone tổng quát an toàn cho mọi object graph: cần quyết định cách xử lý tham chiếu dùng chung, chu trình, object bất biến và object không thể sao chép.

## 8. Component mảng và ngoại lệ về ngữ nghĩa mặc định

Mảng Java là mutable, nhưng record mặc định không so sánh mảng theo nội dung. Mảng kế thừa `Object.equals` và `Object.hashCode`, nên hai record chứa cùng một tham chiếu mảng vẫn bằng nhau dù nội dung mảng thay đổi; hai mảng khác tham chiếu vẫn không bằng nhau dù chứa cùng phần tử.

```java
record ArrayHolder(int[] values) {}

int[] data = {1, 2};
ArrayHolder first = new ArrayHolder(data);
ArrayHolder second = new ArrayHolder(data);

System.out.println(first.equals(second)); // true: cùng tham chiếu mảng

data[0] = 99;
System.out.println(first.equals(second)); // true
```

Trong trường hợp này, mutation nội dung không làm thay đổi equality mặc định vì component được so sánh theo identity của mảng. Tuy nhiên, nếu record tự ghi đè `equals`/`hashCode` để dùng `Arrays.equals`/`Arrays.hashCode` theo nội dung, thay đổi mảng sẽ tác động đến cả hai phương thức. Khi đó cần sao chép phòng vệ trong constructor và accessor; với mảng lồng nhau cần cân nhắc sao chép sâu.

## 9. Component mutable không phải lúc nào cũng làm hash đổi

Không nên kết luận rằng cứ component mutable thì `hashCode` của record chắc chắn thay đổi sau mỗi lần mutation. Tác động phụ thuộc cách component định nghĩa `equals` và `hashCode`:

| Kiểu component | Hành vi mặc định | Mutation nội bộ có thể ảnh hưởng record? |
| --- | --- | --- |
| `ArrayList` | Equality và hash dựa trên phần tử/thứ tự | Có. Thêm, xóa hoặc thay đổi phần tử có thể làm đổi kết quả. |
| Class tự viết có `equals`/`hashCode` theo trường mutable | Dựa trên trạng thái của các trường đó | Có. Thay đổi trường tham gia hai phương thức có thể làm đổi equality/hash. |
| Mảng Java | `Object.equals`/`Object.hashCode` theo identity | Thay đổi phần tử không làm đổi equality/hash mặc định của mảng. |
| Class không ghi đè `equals`/`hashCode` | Theo identity của instance | Thay đổi trạng thái không làm đổi equality/hash mặc định. |
| Record lồng nhau có component mutable | Dựa trên component của record lồng nhau | Có thể, nếu component bên trong dùng equality/hash theo trạng thái mutable. |

Điều cần bảo vệ là **trạng thái mà hợp đồng `equals`/`hashCode` thực sự sử dụng**. Một object có thể mutable nhưng hash không đổi; ngược lại một danh sách mutable có thể làm mã băm thay đổi dù trường tham chiếu của record vẫn là `final`.

## 10. Ghi đè `equals` và `hashCode` không tự giải quyết mutability

Có thể tùy chỉnh hai phương thức để định nghĩa bình đẳng theo yêu cầu nghiệp vụ, nhưng nếu implementation vẫn đọc trực tiếp dữ liệu mutable thì kết quả vẫn có thể thay đổi sau khi tạo record.

Ví dụ:

```java
record MutableKey(List<String> values) {
    @Override
    public boolean equals(Object other) {
        return this == other
            || (other instanceof MutableKey that
                && values.equals(that.values));
    }

    @Override
    public int hashCode() {
        return values.hashCode();
    }
}
```

Hai phương thức trên vẫn dựa trên trạng thái hiện tại của `values`. Muốn giá trị ổn định, hãy bảo vệ component trong constructor và không để lộ tham chiếu mutable qua accessor. Đồng thời, mọi cặp record bằng nhau theo `equals` phải có cùng `hashCode`.

Khi tùy chỉnh `equals` của record, còn phải giữ bất biến sao chép của record: tạo record mới bằng cách truyền kết quả các accessor của record cũ vào canonical constructor phải cho một record bằng record cũ theo `equals`. Thiết kế component bất biến và snapshot rõ ràng giúp đáp ứng yêu cầu này dễ hơn.

## 11. Những nhầm lẫn cần tránh

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| Component là `final` nên nội dung object không thể thay đổi. | **Sai** | `final` chỉ cố định tham chiếu trong trường. |
| Thay đổi `List` component có thể làm đổi `equals` của record. | **Đúng** | `List.equals` dựa trên nội dung và thứ tự. |
| Mọi mutation của mọi component đều làm đổi `hashCode`. | **Sai** | Phụ thuộc semantics `hashCode` của kiểu component. |
| `List.copyOf` tạo bản sao sâu của toàn bộ phần tử. | **Sai** | Nó bảo vệ cấu trúc danh sách, không sao chép sâu object bên trong. |
| Khóa mutable có thể gây lỗi tra cứu trong `HashMap`/`HashSet`. | **Đúng** | Hash hiện tại có thể khác hash lúc chèn. |
| Mảng đổi nội dung sẽ luôn làm đổi hash của record mặc định. | **Sai** | Mảng dùng hash identity mặc định. |
| Ghi đè `equals` là đủ; không cần quan tâm `hashCode`. | **Sai** | Hai phương thức phải nhất quán. |

## 12. Checklist thiết kế record có component mutable

1. Component có mutable không, và những trường nào của nó tham gia `equals`/`hashCode`?
2. Có thể thay component bằng kiểu bất biến như `String`, record lồng nhau bất biến hoặc kiểu `java.time` không?
3. Nếu dùng collection, đã snapshot cấu trúc bằng `List.copyOf`, `Set.copyOf` hoặc `Map.copyOf` chưa?
4. Các phần tử bên trong collection có mutable không? Có cần chuyển thành snapshot bất biến hoặc sao chép sâu không?
5. Nếu component là mảng, yêu cầu equality là theo identity hay theo nội dung?
6. Record có được dùng làm khóa `HashMap` hoặc phần tử `HashSet` sau khi tạo không?
7. Accessor có trả tham chiếu mutable nội bộ ra ngoài không?
8. Nếu tùy chỉnh `equals`/`hashCode`, hai phương thức đã nhất quán và giữ bất biến sao chép của record chưa?

**Ghi nhớ:** Record cố định tham chiếu component, không tự đóng băng object được tham chiếu. Khi component triển khai `equals`/`hashCode` theo trạng thái mutable, thay đổi trạng thái có thể làm thay đổi equality và mã băm của record, gây lỗi khi dùng làm khóa hash collection. Hãy chọn component bất biến hoặc tạo snapshot/sao chép phòng vệ phù hợp với cấu trúc dữ liệu.

## Tài liệu chính thức

- [Java SE 26 API — `java.lang.Record`, hợp đồng `equals`, `hashCode` và copy invariant](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Record.html).
- [Java SE 26 API — `java.util.List.copyOf`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).
- [Java SE 26 API — `java.util.Collection`, hợp đồng equality và hash của collection](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Collection.html).
- [Java Language Specification, Section 8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.10).
- [JEP 395 — Records, tính năng chính thức trong Java 16](https://openjdk.org/jeps/395).
