# Java 10 – Set.copyOf: Lựa chọn đại diện khi nguồn có phần tử trùng

> **Chủ đề:** Java 10 → `Set.copyOf` → **Lựa chọn đại diện khi nguồn có phần tử trùng**. Bài học chỉ dùng các hợp đồng và kỹ thuật vẫn áp dụng trong Java 17+ và JDK hiện đại. `Set.copyOf(Collection)` được bổ sung từ Java 10; `Set.of` xuất hiện từ Java 9. Ví dụ hoàn chỉnh được biên dịch bằng `javac --release 17`.

## 1. Mục tiêu học tập

Sau bài này, bạn sẽ:

1. Giải thích chính xác hành vi `Set.copyOf(source)` khi `source` chứa nhiều đối tượng được xem là bằng nhau.
2. Phân biệt **phần tử trùng theo `equals`** với **bản ghi trùng theo khóa nghiệp vụ**.
3. Hiểu tại sao `Set.copyOf` giữ **một phần tử đại diện bất kỳ**, không cam kết giữ phần tử xuất hiện đầu hay cuối.
4. So sánh cách xử lý phần tử trùng của `List.of`, `Set.of`, `Set.copyOf`, `HashSet` và `LinkedHashSet`.
5. Lựa chọn đại diện một cách xác định theo yêu cầu: **first wins**, **last wins**, hoặc **ưu tiên phiên bản/độ ưu tiên**.
6. Dùng `equals` và `hashCode` nhất quán, giữ dữ liệu làm khóa so sánh ổn định và tránh làm thay đổi object đã nằm trong Set.
7. Hiểu thêm ràng buộc null, thứ tự duyệt, tính không thể sửa, độ sâu của bản sao, thread safety và type inference.
8. Chạy chương trình Java đầy đủ và kiểm tra kết quả mà không phụ thuộc vào một lựa chọn đại diện không được API cam kết.

## 2. Hợp đồng chính thức của `Set.copyOf`

Chữ ký của phương thức:

~~~java
static <E> Set<E> copyOf(Collection<? extends E> coll)
~~~

Đây là phương thức static trong interface `java.util.Set` từ Java 10.

Nó trả về một `Set<E>` **unmodifiable** chứa các phần tử đến từ collection nguồn. Hợp đồng quan trọng nhất của bài này là:

> Nếu collection nguồn có những phần tử trùng nhau, `Set.copyOf` giữ lại **một phần tử bất kỳ** trong nhóm trùng nhau.

Hiểu chính xác lời hứa đó:

- Các phần tử được xem là trùng theo hợp đồng bình đẳng của `Set`, về thực tế dựa trên `equals` và `hashCode` được triển khai đúng.
- Kết quả chỉ giữ **một đại diện** của mỗi nhóm phần tử bằng nhau.
- **Không được suy luận** rằng đại diện luôn là object được thêm vào nguồn trước tiên, cuối cùng, có timestamp mới nhất, hay có payload đầy đủ nhất.
- “Một phần tử bất kỳ” không có nghĩa Java bắt buộc chọn ngẫu nhiên bằng bộ sinh số ngẫu nhiên. Một implementation cụ thể có thể cho kết quả ổn định trong nhiều lần thử, nhưng kết quả ấy **không phải cam kết API**.
- Khi collection nguồn mutable được sửa **sau** khi copy hoàn thành, cấu trúc của `Set` kết quả không tự thay đổi theo nguồn. Điều này không có nghĩa các object phần tử được deep-copy.
- Phương thức từ chối nguồn `null` hoặc nguồn chứa phần tử `null` bằng `NullPointerException`.
- Không thể thêm/bớt/thay phần tử qua API Set kết quả. Thao tác sửa không được hỗ trợ sẽ ném `UnsupportedOperationException`.
- **Thứ tự duyệt** của Set kết quả không được quy định; không dùng thứ tự ấy để suy đoán đại diện được chọn.
- Nếu nguồn đã là một unmodifiable Set phù hợp, implementation có thể tái sử dụng object thay vì tạo object Set mới. Không thiết kế logic dựa trên `result != source`.

Oracle Java SE API ghi rõ hành vi “arbitrary element” tại `Set.copyOf(Collection)`. Đây là khác biệt quan trọng với `Set.of`, vốn **từ chối** các phần tử trùng truyền trực tiếp vào factory.

### 2.1. Phân biệt “số phần tử phân biệt” và “object đại diện”

~~~java
var data = java.util.List.of("red", "red", "blue");
var unique = java.util.Set.copyOf(data);

System.out.println(unique.size()); // 2
~~~

Với String, hai giá trị `"red"` bằng nhau về nội dung và cũng không mang dữ liệu bổ sung cần lựa chọn; ta thường chỉ quan tâm set có hai giá trị phân biệt. Tuy nhiên nếu hai object bằng nhau về khóa nhưng có **metadata khác**, việc chỉ còn một đại diện trở thành quyết định nghiệp vụ quan trọng.

## 3. “Trùng nhau” theo Java nghĩa là gì?

### 3.1. Set dựa vào hợp đồng `equals`, không dựa vào dòng dữ liệu giống nhau về mắt nhìn

Với các object bình thường, Java dùng `equals` để xác định tính bằng nhau theo hợp đồng của class. Mỗi class có thể lựa chọn trường nào tham gia vào so sánh.

~~~java
record Product(String sku, String revision) {}

var first = new Product("p1", "old");
var second = new Product("p1", "new");

System.out.println(first.equals(second)); // false
System.out.println(java.util.Set.copyOf(
        java.util.List.of(first, second)).size()); // 2
~~~

**Vì sao kết quả là 2?** Record mặc định so sánh tất cả component ở trên: `sku` và `revision`. Hai record có cùng `sku` nhưng khác `revision` **không trùng theo `equals`**. Nếu nghiệp vụ định nghĩa “trùng là cùng `sku` bất kể revision”, `Set.copyOf` không tự suy ra quy tắc đó.

Đừng coi việc trùng một trường domain như mã khách hàng hoặc SKU là tương đương với `equals` nếu class chưa triển khai so sánh theo trường đó.

### 3.2. Đối tượng khác identity nhưng bằng nhau theo khóa

Một custom class có thể so sánh dựa trên `id`:

~~~java
final class Candidate {
    private final String id;
    private final String note;

    Candidate(String id, String note) {
        this.id = java.util.Objects.requireNonNull(id);
        this.note = java.util.Objects.requireNonNull(note);
    }

    String id() { return id; }
    String note() { return note; }

    @Override
    public boolean equals(Object other) {
        return other instanceof Candidate c && id.equals(c.id);
    }

    @Override
    public int hashCode() {
        return id.hashCode();
    }
}
~~~

Với class trên:

~~~java
var old = new Candidate("p1", "old");
var fresh = new Candidate("p1", "fresh");

System.out.println(old == fresh);      // false: hai object riêng biệt
System.out.println(old.equals(fresh)); // true: cùng id "p1"
~~~

`Set.copyOf(List.of(old, fresh))` sẽ chứa **một** phần tử đại diện cho id `p1`. Nhưng trường `note` trên object được giữ lại có thể là `old` hoặc `fresh`. Do đó, **không lấy `note` của đại diện tùy ý để quyết định nghiệp vụ** nếu yêu cầu ưu tiên phiên bản cụ thể.

### 3.3. `equals` và `hashCode` là một cặp hợp đồng

Khi override `equals`, phải override `hashCode` tương ứng:

- Nếu `a.equals(b)` là `true`, `a.hashCode()` và `b.hashCode()` bắt buộc bằng nhau.
- `equals` cần nhất quán, phản xạ, đối xứng, bắc cầu và xử lý null theo hợp đồng Java.
- Hai object không bằng nhau **vẫn có thể có cùng hash code**; collision hash không có nghĩa chúng là phần tử trùng.
- Nên sử dụng các giá trị bất biến trong những field tham gia so sánh/hashing khi object được đưa vào Set/Map.

Nếu `equals`/`hashCode` bị triển khai sai hoặc trường làm khóa bị sửa sau khi object vào một Set dựa trên hash, kết quả của `contains`/khả năng tìm kiếm có thể trở nên sai hoặc khó dự đoán. Không “khắc phục” lỗi đó bằng cách gọi `Set.copyOf` nhiều lần.

## 4. Đại diện tùy ý: điều được bảo đảm và điều không được bảo đảm

Hãy tưởng tượng nguồn có:

| Vị trí trong List | `id` | `note` | So sánh `equals` theo `id` |
| --- | --- | --- | --- |
| 0 | `p1` | `old` | Bằng phần tử ở vị trí 1 |
| 1 | `p1` | `fresh` | Bằng phần tử ở vị trí 0 |
| 2 | `p2` | `only` | Khác hai phần tử trên |

Sau:

~~~java
var copied = java.util.Set.copyOf(
        java.util.List.of(old, fresh, only));
~~~

Ta **được bảo đảm**:

- `copied.size() == 2`, nếu `equals`/`hashCode` đúng như thiết kế.
- Có đúng một đại diện thuộc nhóm id `p1`, và một phần tử thuộc nhóm id `p2`.
- Phần tử được giữ của id `p1` bằng theo `equals` với cả `old` và `fresh`.
- Nội dung Set không bị sửa cấu trúc qua API Set.

Ta **không được bảo đảm**:

- `copied` giữ `old` chỉ vì `old` đứng trước.
- `copied` giữ `fresh` chỉ vì `fresh` đứng sau.
- Đại diện được chọn dựa trên phiên bản, timestamp, độ ưu tiên hay giá.
- Duyệt `copied` ra `p1` trước `p2`.
- Lựa chọn đại diện vẫn giống nhau khi đổi JDK, môi trường, implementation hoặc chiến lược nội bộ.

Cách kiểm thử hợp lệ là kiểm tra đại diện thuộc **một trong các object trùng của nguồn**, thay vì áp đặt một lựa chọn cụ thể:

~~~java
var chosen = copied.stream()
        .filter(c -> c.id().equals("p1"))
        .findFirst().orElseThrow();

boolean fromInput = chosen == old || chosen == fresh;
System.out.println(fromInput); // true
~~~

Không viết bài kiểm thử kiểu `assertSame(old, chosen)` hoặc `assertEquals("fresh", chosen.note())` vì Set API không hứa chọn first/last. Nếu hệ thống cần assert như vậy, **phải thực hiện chính sách chọn đại diện trước**.

## 5. So sánh cách xử lý trùng giữa những collection thông dụng

| API/cấu trúc | Khi có phần tử trùng theo `equals` | Bảo toàn thứ tự? | Có cho sửa collection? |
| --- | --- | --- | --- |
| `List.of("A", "A")` | Giữ cả hai phần tử | Có, theo vị trí input | Không |
| `Set.of("A", "A")` | Ném `IllegalArgumentException` | Không có kết quả | Không |
| `Set.copyOf(List.of("A", "A"))` | Gộp còn một; đại diện tùy ý | Không cam kết | Không |
| `new HashSet<>(source)` | Loại các phần tử trùng khi thêm | Không cam kết thứ tự duyệt | Có |
| `new LinkedHashSet<>(source)` | Giữ phần tử được thêm thành công đầu tiên của mỗi nhóm trùng | Giữ insertion order của phần tử phân biệt | Có |
| `new LinkedHashMap<K,V>()` + `putIfAbsent` | **First wins** theo key đã chỉ định | Giữ thứ tự thêm key đầu tiên | Có |
| `new LinkedHashMap<K,V>()` + `put` | **Last wins** theo key đã chỉ định | Giữ thứ tự thêm key đầu tiên cho map insertion-order | Có |

Phân biệt:

- `Set.of` kiểm tra trùng ngay trong các đối số đầu vào và **ném lỗi**; `Set.copyOf` chấp nhận collection có phần tử trùng và gộp các giá trị bằng nhau.
- `HashSet` và `LinkedHashSet` không tự tạo immutable result; nếu cần công bố kết quả không cho sửa, có thể tạo snapshot sau bước xử lý trùng.
- `LinkedHashSet` có thể cho chiến lược “first wins” đối với **cách bằng nhau do `equals` định nghĩa**, khi source được duyệt theo thứ tự ổn định. Nếu cần trùng theo một **key riêng khác `equals`**, nên dùng Map keyed by that key.
- `Set.copyOf` không phải công cụ chọn “last wins”, cũng không có overload truyền `Comparator` hoặc merge function để định chính sách đại diện.
- `LinkedHashMap` giữ thứ tự insertion của key, kể cả khi `put` cập nhật value của key đã tồn tại. Khi cuối cùng biến thành Set qua `Set.copyOf`, không được tiếp tục kỳ vọng thứ tự duyệt ấy được giữ.

### 5.1. Không nhầm với `Set.of`

~~~java
try {
    java.util.Set.of("A", "A");
} catch (IllegalArgumentException e) {
    System.out.println("duplicate rejected"); // chạy vào đây
}

var accepted = java.util.Set.copyOf(java.util.List.of("A", "A"));
System.out.println(accepted.size()); // 1
~~~

Nguồn của `Set.copyOf` đã là một `Collection`; List cho phép các phần tử trùng. Ngược lại, `Set.of` là factory nhận danh sách các giá trị để tạo Set mới và từ chối các giá trị trùng nhau. Hai API không được dùng thay thế một cách vô điều kiện.

## 6. Cần **first wins**: chọn đại diện trước khi tạo snapshot

Ví dụ yêu cầu “nếu hai bản ghi có cùng SKU, giữ bản xuất hiện đầu tiên trong một danh sách đã có thứ tự xác định”.

Sử dụng `LinkedHashMap`:

~~~java
var firstWins = new java.util.LinkedHashMap<String, Candidate>();

for (var candidate : input) {
    firstWins.putIfAbsent(candidate.id(), candidate);
}

var chosenFirst = firstWins.get("p1"); // object đến trước theo input
var result = java.util.Set.copyOf(firstWins.values());
~~~

Giải thích:

1. `candidate.id()` là **khóa nghiệp vụ**. Đó là quy tắc trùng do chương trình chủ động xác định.
2. `putIfAbsent` chỉ đặt value khi key chưa có mapping; vì source đã được kiểm soát null, lần xuất hiện sau không thay thế lần trước.
3. `firstWins.values()` có một đại diện cho mỗi key. Nếu các key định nghĩa đúng nhóm duy nhất theo `equals` của Candidate, `Set.copyOf` không còn phải lựa chọn giữa hai object có id trùng.
4. `result` unmodifiable nhưng không có thứ tự duyệt được cam kết.
5. Nếu thứ tự kết quả là hợp đồng API, dùng `List.copyOf(firstWins.values())` thay vì ép qua Set; List bảo toàn thứ tự duyệt giá trị của LinkedHashMap insertion-order.

Điều kiện bắt buộc: “đầu tiên” phải có ý nghĩa. Với nguồn là `List` có thứ tự xác định, ta biết encounter order. Với kết quả database thiếu `ORDER BY`, `HashSet` hoặc stream unordered, khái niệm “đầu tiên” có thể không ổn định qua các lần chạy.

**Lưu ý về null:** `putIfAbsent` được định nghĩa để cập nhật cả khi mapping hiện là null. Nếu nghiệp vụ cho phép null value và vẫn coi key đã tồn tại là “đã chọn”, hãy dùng `containsKey` và chính sách null tường minh; ví dụ ở đây dùng `Candidate` khác null để tránh mơ hồ.

## 7. Cần **last wins**: chủ động ghi đè value theo key

Với chính danh sách có thứ tự:

~~~java
var lastWins = new java.util.LinkedHashMap<String, Candidate>();

for (var candidate : input) {
    lastWins.put(candidate.id(), candidate);
}

var chosenLast = lastWins.get("p1"); // object có id p1 ở lần xuất hiện cuối
var result = java.util.Set.copyOf(lastWins.values());
~~~

Mỗi `put` với key đã có sẽ **thay value**, tạo chính sách last wins. Vì map có duy nhất một value mỗi key, `Set.copyOf(lastWins.values())` không còn phải giải quyết các bản ghi trùng theo key.

Cần chú ý: `lastWins` là `LinkedHashMap` mặc định insertion-order. Dù value của `p1` được thay bằng bản cuối, vị trí key `p1` trong thứ tự duyệt map vẫn là vị trí nó xuất hiện lần đầu. Nếu muốn thứ tự “lần cuối xuất hiện” cho output, phải xây chính sách sắp xếp riêng, không được cho rằng thay value sẽ đẩy key xuống cuối.

### 7.1. Khi duplicate được định nghĩa bằng `equals`, có thể dùng `LinkedHashSet`

~~~java
var firstSeen = new java.util.LinkedHashSet<>(input);
var frozen = java.util.Set.copyOf(firstSeen);
~~~

Với một nguồn có thứ tự và `equals` đúng, `LinkedHashSet.add` lần đầu giữ đại diện đầu tiên; lần thêm object bằng nhau sau đó không thay nó. `Set.copyOf(firstSeen)` nhận source không còn phần tử trùng, nên đại diện đã được chọn từ trước. Tuy nhiên **thứ tự của `frozen` vẫn không được cam kết**, nên nếu cần thứ tự hãy giữ `List.copyOf(firstSeen)`.

Không áp dụng chiến lược này khi domain định nghĩa trùng theo một trường không nằm trong `equals`; lúc ấy dùng Map theo khóa rõ ràng.

## 8. Cần “bản tốt nhất” – chính sách dựa trên phiên bản, thời gian hoặc độ ưu tiên

“Đầu tiên”/“cuối cùng” thường không đủ cho dữ liệu production. Ví dụ nghiệp vụ muốn giữ bản ghi có revision lớn nhất cho mỗi SKU, bất kể thứ tự input.

Một chính sách rõ ràng:

~~~java
record VersionedProduct(String sku, long version, String description) {}

var winners = new java.util.LinkedHashMap<String, VersionedProduct>();
for (var item : products) {
    winners.merge(item.sku(), item, (current, incoming) -> {
        if (incoming.version() > current.version()) return incoming;
        if (incoming.version() < current.version()) return current;
        // Ví dụ: nếu phiên bản bằng nhau, chọn mô tả nhỏ hơn theo từ điển.
        return incoming.description().compareTo(current.description()) < 0
                ? incoming : current;
    });
}

var chosen = java.util.List.copyOf(winners.values());
~~~

Đây là **đoạn minh họa đặt trong một phương thức có biến `products` kiểu `Collection<VersionedProduct>` hoặc `List<VersionedProduct>`**, không phải toàn bộ chương trình độc lập.

Ưu điểm:

- Domain key là `sku`, không cần ép định nghĩa `equals` của record theo SKU.
- Quy tắc chọn bản ghi cao nhất được viết và kiểm thử rõ ràng.
- Tie-breaker được xác định, tránh phụ thuộc vào thứ tự input khi `version` bằng nhau (nếu cả `version` và `description` bằng nhau, khác biệt về object identity không còn ý nghĩa trong ví dụ).
- Có thể thay tie-breaker theo yêu cầu thực, ví dụ nguồn ưu tiên hơn, trạng thái đã duyệt, timestamp chuẩn hóa hoặc báo lỗi khi xung đột.

Những lưu ý:

- Với record `VersionedProduct`, `equals` mặc định so sánh **cả ba component**, không chỉ `sku`. Gọi `Set.copyOf(products)` sẽ **không tự** gộp hai record khác `version` chỉ vì cùng SKU.
- Nếu dùng timestamp, cần xác định cách xử lý cùng timestamp, timezone/chất lượng dữ liệu và thứ tự nguồn; không suy đoán chính sách business từ iterator của Set.
- `Map.merge` là một API có từ trước và vẫn áp dụng; đối số merge phải có giá trị không-null. Khi có concurrency hoặc source không ổn định, nên thiết kế điều phối phù hợp thay vì giả định một `LinkedHashMap` thông thường thread-safe.

## 9. Xác định đúng **định nghĩa duplicate** trước khi dùng `Set.copyOf`

Các tình huống thường gặp:

| Bài toán | Định nghĩa “trùng” thực sự | Công cụ phù hợp |
| --- | --- | --- |
| Danh sách tag String | Hai String có cùng nội dung theo `equals` | `Set.copyOf(tags)` nếu không quan tâm thứ tự |
| Danh sách mã số | Hai object Integer bằng giá trị | `Set.copyOf` với source không chứa null |
| Product record có SKU và revision | Trùng toàn bộ component record, hay trùng SKU? | Xác định trước; dùng Map keyed SKU nếu nghiệp vụ theo SKU |
| User entity từ database | Cùng ID nhưng object có field khác nhau | Dùng Map keyed ID và chính sách dữ liệu mới/cũ |
| Sự kiện có cùng event key | Cùng key, cần giữ bản có timestamp mới | Map + merge theo timestamp và tie-breaker |
| Các giá trị cần giữ cả bản trùng | Mỗi lần xuất hiện là dữ liệu có ý nghĩa | Dùng `List`, không chuyển sang Set |
| Danh sách cần thứ tự xác định | Uniqueness + encounter order | `LinkedHashSet`/`LinkedHashMap` rồi `List.copyOf` |
| Muốn từ chối trùng như dữ liệu lỗi | Có duplicate là invalid input | Kiểm tra trùng chủ động, ném exception có thông điệp cụ thể |

Lỗi thiết kế phổ biến là coi `Set.copyOf` như một phép `deduplicateByKey` chung. Nó chỉ hiểu `equals` hiện tại của element type. Nếu khóa nghiệp vụ khác `equals` hoặc quy tắc chọn đại diện quan trọng, cần một bước xử lý riêng.

### 9.1. Không sửa `equals` chỉ để làm một màn hình hết bản ghi trùng

`equals` của một class ảnh hưởng mọi nơi class đó xuất hiện trong Set/Map và các phép so sánh, không chỉ một màn hình. Nếu ứng dụng có hai chính sách khác nhau, ví dụ một API coi duplicate theo `sku`, API khác theo `(sku, revision)`, tốt hơn là giữ value object có hợp đồng equality rõ ràng và dùng Map keyed by `sku` hoặc record key hỗn hợp tùy ngữ cảnh, thay vì liên tục thay semantics `equals`.

## 10. Tính bất biến của kết quả và giới hạn của bản sao

### 10.1. Unmodifiable Set không đồng nghĩa deep immutable

~~~java
final class MutableItem {
    String id;
    MutableItem(String id) { this.id = id; }
}

var item = new MutableItem("A");
var result = java.util.Set.copyOf(java.util.List.of(item));
item.id = "B"; // object bên trong có thể đã thay đổi
~~~

Ví dụ chỉ minh họa một Set unmodifiable **không ngăn sửa element**. Trong class này `equals`/`hashCode` vẫn dùng identity mặc định, nên sửa `id` không làm đổi khóa hash theo identity. Nếu class override `equals`/`hashCode` dựa vào field mutable `id`, việc sửa `id` sau khi thêm vào Set nguy hiểm hơn nhiều: lookup có thể mất tính nhất quán.

Cách phòng tránh:

- Ưu tiên element immutable (record hợp lệ, String, value object với field final và không leak mutable state).
- Nếu element có list/array lồng nhau, thực hiện defensive copying theo nhu cầu.
- Không sửa các field tham gia `equals`/`hashCode` khi object đang là phần tử của hash-based collection.
- Trong cơ chế lưu/truyền nhiều luồng, xem xét thêm safe publication và quyền sở hữu object.

### 10.2. Sau khi copy, sửa nguồn không làm thay đổi **cấu trúc** Set kết quả

~~~java
var input = new java.util.ArrayList<>(java.util.List.of("A", "B"));
var snapshot = java.util.Set.copyOf(input);
input.add("C");

System.out.println(snapshot.size()); // 2
~~~

Kết quả không tự nhận phần tử `C` được thêm sau. Nhưng nếu source giữ một tham chiếu đến một **object phần tử mutable** và sửa object đó, việc quan sát element qua `snapshot` có thể thay đổi. `Set.copyOf` không clone các phần tử.

### 10.3. Không dựa vào iteration order và identity

~~~java
var unique = java.util.Set.copyOf(java.util.List.of("A", "B"));
~~~

Không dùng `unique.iterator().next()` để khẳng định `"A"` là phần tử đầu tiên. Nếu cần output có thứ tự, tạo một danh sách đã sắp xếp:

~~~java
var ordered = unique.stream().sorted().toList(); // Java 16+
System.out.println(ordered); // [A, B]
~~~

Nếu dùng Java 17+, `Stream.toList()` có thể tạo danh sách không cho sửa; với phần tử `String` thì kết quả phù hợp để công bố.

Các instance trả từ unmodifiable factories được mô tả là value-based; không thiết kế cache identity hoặc `synchronized(result)` dựa trên tham chiếu của chúng. Nếu cần monitor, tạo một object khóa riêng do ứng dụng sở hữu.

## 11. Null, generic type inference và các lỗi đầu vào

### 11.1. Nguồn null hoặc phần tử null

~~~java
var withNull = new java.util.ArrayList<String>();
withNull.add(null);

// java.util.Set.copyOf(withNull); // ném NullPointerException khi chạy
// java.util.Set.copyOf(null);     // ném NullPointerException khi chạy
~~~

Nếu nguồn đến từ hệ thống ngoài và null có ý nghĩa, hãy chọn chính sách trước: loại null, thay bằng giá trị domain hợp lệ, hoặc từ chối input với thông điệp rõ. Không để null tình cờ đi vào factory và dựa vào exception mơ hồ cho luồng nghiệp vụ cần validation chi tiết.

### 11.2. Generic type của `Set.copyOf`

~~~java
java.util.List<String> names = java.util.List.of("An", "Binh");
var uniqueNames = java.util.Set.copyOf(names); // Set<String>

var emptyUnknown = java.util.Set.copyOf(java.util.List.of()); // Set<Object>
var emptyTyped = java.util.Set.copyOf(
        java.util.List.<String>of()); // Set<String>
~~~

`var` (Java 10) suy luận theo kiểu kết quả của initializer. Nếu collection rỗng không có thông tin `E` trong constructor/factory và cũng không có target type, `Object` có thể được chọn. Điều này **khác** vấn đề chọn một đại diện khi các phần tử trùng nhau: một cái là **suy luận generic tại compile time**, cái kia là **loại trùng theo equals khi xây Set**.

Khi cần giao diện API công khai, hãy dùng kiểu tường minh phù hợp:

~~~java
public static java.util.Set<String> uniqueLabels(
        java.util.Collection<String> source) {
    return java.util.Set.copyOf(source);
}
~~~

Caller nhận hợp đồng `Set<String>`; function này không hứa phần tử nào là đại diện nếu nguồn có các object khác nhau nhưng cùng equality key. Với String cùng nội dung, sự khác biệt đại diện thường không ảnh hưởng kết quả nghiệp vụ.

### 11.3. Không đồng nhất `Set.copyOf` và `new HashSet<>(source)`

`new HashSet<>(source)` tạo Set **mutable**, có thể chấp nhận null và không cam kết thứ tự duyệt; `Set.copyOf(source)` từ chối null và trả Set unmodifiable. Cả hai dùng khái niệm phần tử trùng của Set, nhưng các hợp đồng khác nhau. Nếu cần kiểm soát đại diện chính xác, xử lý explicit trước khi tạo kết quả không cho sửa.

## 12. Concurrency: nguồn thay đổi trong lúc copy và element mutable

Không có cam kết rằng `Set.copyOf(source)` là một snapshot atomic của một `ArrayList` đang bị thread khác chỉnh sửa cùng lúc. Nếu copy và mutate nguồn không có đồng bộ, có nguy cơ data race hoặc kết quả không nhất quán.

Với nguồn mutable được chia sẻ, hãy chọn một trong các cách:

- Bảo vệ **cả thay đổi nguồn và thao tác copy** bằng cùng một khóa.
- Chuẩn bị dữ liệu trong thread xử lý và tạo snapshot trước khi chia sẻ.
- Dùng concurrent collection và giao thức snapshot phù hợp; đừng coi mọi iterator concurrent là snapshot atomic.
- Công bố kết quả sang thread khác qua phương tiện có `happens-before` rõ ràng (`volatile`, khóa, task handoff, `Future.get`...) nếu cần đảm bảo visibility.

~~~java
final class SafeSource {
    private final Object lock = new Object();
    private final java.util.List<Candidate> data = new java.util.ArrayList<>();

    void add(Candidate value) {
        synchronized (lock) {
            data.add(value);
        }
    }

    java.util.Set<Candidate> snapshot() {
        synchronized (lock) {
            return java.util.Set.copyOf(data);
        }
    }
}
~~~

Đây là **đoạn minh họa sử dụng class Candidate đã định nghĩa**, không phải chương trình độc lập. Cùng monitor `lock` ngăn một lần `add` chạy đồng thời với `snapshot` trong class. Nếu caller có alias đến `data` và sửa bên ngoài khóa, bảo đảm này bị phá vỡ. Dữ liệu `Candidate` cần immutable hoặc được bảo vệ tiếp nếu các reader dùng chung nhiều thread.

### 12.1. Chi phí, độ lớn dữ liệu và nhịp cập nhật

Tạo Set từ collection yêu cầu duyệt/deduplicate các phần tử và cần tài nguyên tỷ lệ với đầu vào; không gọi `Set.copyOf` lặp lại trong hot loop chỉ để “bảo đảm chọn đại diện mới”. Nếu cần cập nhật từng phần tử liên tục, giữ một cấu trúc mutable/concurrent có chủ sở hữu rõ ràng và publish snapshot theo đợt. Nếu chỉ cần lấy số phần tử khác nhau, có thể sử dụng Set thích hợp nhưng vẫn phải xác định “trùng” theo equality đúng.

## 13. Ví dụ Java 17+ hoàn chỉnh và stdout đã kiểm chứng

Chương trình sau chủ động **không in note của đại diện tùy ý** do `Set.copyOf` giữ lại. Thay vào đó, nó xác minh đại diện đến từ input và có khóa đúng; sau đó chạy **first wins** và **last wins** bằng `LinkedHashMap` để có đầu ra xác định.

Lưu file đúng tên **`SetCopyRepresentativeDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class SetCopyRepresentativeDemo {
    static final class Candidate {
        private final String id;
        private final String variant;

        Candidate(String id, String variant) {
            this.id = Objects.requireNonNull(id);
            this.variant = Objects.requireNonNull(variant);
        }

        String id() { return id; }
        String variant() { return variant; }

        @Override
        public boolean equals(Object other) {
            return other instanceof Candidate candidate
                    && id.equals(candidate.id);
        }

        @Override
        public int hashCode() {
            return id.hashCode();
        }

        @Override
        public String toString() {
            return id + ":" + variant;
        }
    }

    public static void main(String[] args) {
        var old = new Candidate("p1", "old");
        var fresh = new Candidate("p1", "fresh");
        var only = new Candidate("p2", "only");

        var input = new ArrayList<>(List.of(old, fresh, only));
        var arbitrary = Set.copyOf(input);

        var selected = arbitrary.stream()
                .filter(candidate -> candidate.id().equals("p1"))
                .findFirst().orElseThrow();

        System.out.println("unique-count=" + arbitrary.size());
        System.out.println("selected-is-input="
                + (selected == old || selected == fresh));
        System.out.println("selected-key=" + selected.id());
        System.out.println("contains-equivalent="
                + arbitrary.contains(new Candidate("p1", "another")));

        input.add(new Candidate("p3", "later"));
        System.out.println("source-size=" + input.size());
        System.out.println("snapshot-size=" + arbitrary.size());

        try {
            arbitrary.add(new Candidate("p4", "extra"));
        } catch (UnsupportedOperationException expected) {
            System.out.println("copy-mutation=blocked");
        }

        try {
            Set.of(old, fresh);
        } catch (IllegalArgumentException expected) {
            System.out.println("set-of-duplicates=rejected");
        }

        var withNull = new ArrayList<String>();
        withNull.add(null);
        try {
            Set.copyOf(withNull);
        } catch (NullPointerException expected) {
            System.out.println("copy-null=rejected");
        }

        var original = List.of(old, fresh, only);
        var firstWins = new LinkedHashMap<String, Candidate>();
        var lastWins = new LinkedHashMap<String, Candidate>();

        for (var candidate : original) {
            firstWins.putIfAbsent(candidate.id(), candidate);
            lastWins.put(candidate.id(), candidate);
        }

        System.out.println("first-wins=" + firstWins.get("p1").variant());
        System.out.println("last-wins=" + lastWins.get("p1").variant());
        System.out.println("first-set-size="
                + Set.copyOf(firstWins.values()).size());
        System.out.println("last-set-size="
                + Set.copyOf(lastWins.values()).size());
        System.out.println("ordered-ids=" + firstWins.keySet());
        System.out.println("ordered-variants="
                + List.copyOf(firstWins.values()).stream()
                    .map(Candidate::variant).toList());
        System.out.println("strings-deduplicated="
                + Set.copyOf(List.of("X", "X", "Y")).size());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 SetCopyRepresentativeDemo.java
java SetCopyRepresentativeDemo
~~~

**Stdout chính xác** của chương trình (đã biên dịch và chạy trên JDK hiện đại):

~~~text
unique-count=2
selected-is-input=true
selected-key=p1
contains-equivalent=true
source-size=4
snapshot-size=2
copy-mutation=blocked
set-of-duplicates=rejected
copy-null=rejected
first-wins=old
last-wins=fresh
first-set-size=2
last-set-size=2
ordered-ids=[p1, p2]
ordered-variants=[old, only]
strings-deduplicated=2
~~~

### 13.1. Phân tích các dòng kết quả

1. `unique-count=2`: input ban đầu có ba Candidate nhưng hai Candidate mang id `p1` bằng nhau theo `equals`.
2. `selected-is-input=true` và `selected-key=p1`: đại diện của nhóm `p1` là một trong các phần tử nguồn. Chương trình **không giả định** nó là `old` hay `fresh`.
3. `contains-equivalent=true`: Candidate mới có cùng id `p1` được coi là bằng đại diện trong Set mặc dù variant khác nhau; điều này xuất phát từ định nghĩa `equals` của class.
4. `source-size=4` và `snapshot-size=2`: thêm phần tử vào nguồn sau `copyOf` không sửa cấu trúc của snapshot đã tạo.
5. `copy-mutation=blocked`: kết quả `Set.copyOf` unmodifiable.
6. `set-of-duplicates=rejected`: factory `Set.of` ném `IllegalArgumentException` vì hai Candidate bằng nhau.
7. `copy-null=rejected`: `Set.copyOf` từ chối phần tử `null`.
8. `first-wins=old` và `last-wins=fresh`: lần đầu/ cuối được **chọn chủ động bằng Map**, không dựa vào may rủi của `copyOf`.
9. `first-set-size=2`, `last-set-size=2`: hai Map đã có duy nhất một value mỗi key, nên việc chuyển sang Set không phải xử lý xung đột id nữa.
10. `ordered-ids=[p1, p2]` và `ordered-variants=[old, only]`: thứ tự này đến từ `LinkedHashMap` và `List.copyOf(map.values())`, **không** phải từ `Set.copyOf`.
11. `strings-deduplicated=2`: hai chuỗi X bằng nhau được gộp thành một đại diện về mặt giá trị.

### 13.2. Vì sao ví dụ không in phần tử đại diện tùy ý?

Nếu viết `System.out.println(selected.variant());`, stdout có thể là `old` hoặc `fresh`; việc khẳng định một trong hai là “output chuẩn” sẽ tạo bài học sai về hợp đồng Java. Khi dạy và test API có **unspecified representative**, hãy kiểm tra bất biến chung như số nhóm, khóa và tính thuộc nguồn, rồi dùng chính sách explicit nếu giá trị payload của đại diện phải xác định.

## 14. Lỗi thường gặp và cách sửa

| Lỗi tư duy hoặc code | Hậu quả | Cách xử lý |
| --- | --- | --- |
| “`Set.copyOf` luôn giữ phần tử đầu tiên” | Phụ thuộc chi tiết implementation | Dùng `putIfAbsent`/`LinkedHashSet` khi có encounter order rõ |
| “`Set.copyOf` luôn giữ phần tử cuối cùng” | Có thể giữ object cũ | Dùng `Map.put` theo key |
| “`Set.of` và `Set.copyOf` cùng loại bỏ trùng” | `Set.of` **ném exception** khi input trùng | Chọn đúng API theo chính sách validate |
| “Cùng SKU nghĩa là `equals` bằng nhau” | Record có thể so sánh thêm revision | Xác định key nghiệp vụ riêng |
| “Hash code bằng nhau nên là duplicate” | Collision hash không tương đương equality | Viết đúng `equals`/`hashCode` |
| “Chỉ override `equals` là đủ” | Hash-based Set hoạt động không nhất quán | Override `hashCode` tương ứng |
| “Dựa vào `iterator().next()` để chọn best” | Thứ tự Set không được cam kết | So sánh theo business comparator hoặc Map merge |
| “`Set.copyOf` tạo deep copy” | Element mutable vẫn có thể đổi | Immutable elements và defensive copying |
| “`Set.copyOf` chấp nhận null” | Ném `NullPointerException` | Validate/loại null có chủ ý |
| “Sửa source về sau sẽ đổi kết quả” | Snapshot không tự cập nhật cấu trúc | Tạo snapshot mới nếu cần |
| “`Set.copyOf` luôn cấp phát Set mới” | Có thể tái sử dụng unmodifiable Set | Không phụ thuộc object identity |
| “`LinkedHashMap.put` chuyển key xuống cuối” | Map insertion-order giữ vị trí key đầu | Nếu muốn order theo lần cuối, sắp xếp lại rõ ràng |
| “Dùng `HashSet` là cách sắp xếp ổn định” | HashSet không cam kết iteration order | Dùng `LinkedHashSet`/Map + List/sort |
| “Copy từ ArrayList đang bị sửa đồng thời vẫn atomic” | Không có snapshot giao dịch được đảm bảo | Đồng bộ writer/copy hoặc dùng thiết kế snapshot riêng |
| “Unit test trên một JDK thấy giữ old thì đó là contract” | Test đang kiểm tra implementation detail | Chỉ assert những điều Java API cam kết |

## 15. Bài tập tự kiểm tra kèm đáp án

**Bài 1.** Kết quả `Set.copyOf(List.of("a", "a", "b")).size()` là bao nhiêu?

**Đáp án:** `2`. Hai giá trị String `"a"` bằng nhau và chỉ có một đại diện.

**Bài 2.** Điều gì xảy ra với `Set.of("a", "a")`?

**Đáp án:** Ném `IllegalArgumentException` khi tạo Set; khác với `Set.copyOf` vốn chấp nhận collection có phần tử trùng và gộp.

**Bài 3.** Hai Candidate khác object nhưng `equals` chỉ xét cùng id, metadata khác nhau. `Set.copyOf` có đảm bảo giữ metadata của Candidate đầu tiên không?

**Đáp án:** Không. Nó giữ một đại diện tùy ý trong nhóm bằng nhau. Nếu metadata quan trọng, chọn đại diện theo quy tắc business trước khi đóng băng collection.

**Bài 4.** Record `record Product(String id,String rev){}` có hai bản cùng id nhưng khác rev. `Set.copyOf` có loại một bản không?

**Đáp án:** Không, với `equals` được record tạo mặc định (so sánh cả id và rev), hai record không bằng nhau. Nếu trùng được định nghĩa theo id, dùng Map keyed id hoặc kiểu equality riêng có chủ đích.

**Bài 5.** Vì sao `Set.copyOf` không nên được dùng để tự chọn phiên bản mới nhất?

**Đáp án:** API không biết/không cam kết quy tắc theo timestamp hay version. Cần explicit comparator/merge function chọn bản mới nhất và tie-breaker.

**Bài 6.** Cách chọn first wins với một List có thứ tự?

**Đáp án:** Duyệt List theo encounter order, đưa vào `LinkedHashMap<K,V>` bằng `putIfAbsent(key, item)`. Nếu cần Set không cho sửa, tạo `Set.copyOf(map.values())`; nếu cần giữ thứ tự, dùng `List.copyOf(map.values())`.

**Bài 7.** Cách chọn last wins với cùng List?

**Đáp án:** Duyệt List và gọi `map.put(key, item)`. Value của key đã có được thay bằng item sau cùng; vị trí key trong insertion-order LinkedHashMap không tự chuyển xuống cuối.

**Bài 8.** Nếu đầu vào là `HashSet`, “phần tử đầu tiên” có nghĩa ổn định không?

**Đáp án:** Không theo một thứ tự nghiệp vụ đáng tin vì HashSet không cam kết thứ tự duyệt. Phải có sequence/order rõ trước khi áp dụng first/last wins, hoặc chọn theo comparator independent of iteration order.

**Bài 9.** Sau `var result = Set.copyOf(source);`, thay đổi cấu trúc `source` có làm tăng số phần tử result không?

**Đáp án:** Không khi source được sửa sau lúc copy hoàn tất. Nhưng `Set.copyOf` không sao chép sâu object phần tử.

**Bài 10.** Vì sao field dùng trong `hashCode` nên immutable khi object là element của Set?

**Đáp án:** Vì sửa field làm thay đổi hash/equality trong khi object đã được định vị trong cấu trúc hash theo giá trị trước, có thể khiến `contains` hoạt động không đáng tin.

**Bài 11.** `Set.copyOf` có chấp nhận List chứa null không?

**Đáp án:** Không. Nó ném `NullPointerException`. Không dùng `List.of(null)` để thử chính sách này vì `List.of` đã từ chối null trước khi Set.copyOf được gọi.

**Bài 12.** Nếu cần kết quả vừa unique theo key vừa giữ thứ tự input, có nên trả thẳng `Set.copyOf(map.values())` không?

**Đáp án:** Không, nếu thứ tự là hợp đồng. Hãy dùng `List.copyOf(linkedHashMap.values())`, hoặc sắp xếp danh sách theo comparator cụ thể.

**Bài 13.** Một implementation hôm nay giữ đại diện cuối trong `Set.copyOf`. Có nên viết test `assertSame(last, chosen)` không?

**Đáp án:** Không. Đây là hành vi không được API bảo đảm. Test nên kiểm tra phần tử tồn tại theo equality, số nhóm và các bất biến được cam kết.

**Bài 14.** Tại sao `Set.copyOf` có thể đúng để loại trùng các String, nhưng có thể sai để xử lý hàng loạt user entity từ database?

**Đáp án:** String có equality rõ và giá trị trùng thường không phân biệt được về nghiệp vụ. Entity có thể chứa version, timestamp, vai trò hoặc dữ liệu xung đột; phải xác định domain key và quy tắc đại diện.

**Bài 15.** Với nhiều thread đang sửa ArrayList nguồn, chỉ `Set.copyOf(arrayList)` đã đủ để đảm bảo snapshot nhất quán chưa?

**Đáp án:** Chưa. Cần bảo vệ việc mutate/copy hoặc chọn kiến trúc snapshot phù hợp; Set.copyOf không khóa nguồn.

**Bài 16.** `Set.copyOf` có chắc trả một object Set mới, không cùng identity với nguồn không?

**Đáp án:** Không. Implementation có thể dùng lại nguồn unmodifiable Set phù hợp; thiết kế dựa trên các giá trị và hợp đồng của Set, không dựa trên identity hay synchronization trên các object value-based.

## 16. Checklist triển khai thực tế

Trước khi dùng `Set.copyOf` để xử lý duplicate trong code production, hãy kiểm tra:

1. **Khóa trùng là gì?** Java `equals`, business id, tổ hợp trường, hay một chính sách khác?
2. **Đại diện có quan trọng không?** Những object equal có metadata khác nhau không?
3. **Chính sách chọn là gì?** Any, first, last, max version, priority hoặc reject duplicates?
4. **Thứ tự nguồn có xác định không?** List, kết quả SQL có ORDER BY, stream ordered hay nguồn không có thứ tự?
5. **Tie-breaker có xác định không?** Khi version/timestamp bằng nhau, chọn gì?
6. **Element equality có đúng không?** `equals`/`hashCode` nhất quán, không phụ thuộc field mutable sau khi được đưa vào Set?
7. **Có null không?** Đã validate đầu vào và thông điệp lỗi chưa?
8. **Output cần immutable cấu trúc hay immutable sâu?** Có mutable entity nào còn alias?
9. **Output có cần thứ tự không?** Nếu có, dùng List/sort/LinkedHashMap trước, không dựa iteration order của Set.copyOf.
10. **Có nhiều thread không?** Đã có giao thức snapshot và safe publication phù hợp chưa?
11. **Đã test đúng hợp đồng chưa?** Không assert first/last nếu chỉ dùng Set.copyOf.
12. **Chi phí có phù hợp không?** Không tạo lại cả Set liên tục khi dữ liệu lớn và update tần suất cao.

## 17. Tài liệu tham khảo chính thức

1. [Java SE 17 – Set.copyOf(Collection)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)): mô tả chính xác việc giữ một phần tử đại diện tùy ý khi nguồn trùng, từ chối null và không phản ánh sửa đổi nguồn về sau.
2. [Java SE 25 – Set interface](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Set.html): hợp đồng Set, `Set.of`, `Set.copyOf`, các đặc tính unmodifiable, iteration order và value-based.
3. [Java SE 17 – Object.equals và hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): hợp đồng bình đẳng và tương thích hash code.
4. [Java SE 17 – LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html): insertion-order, `put` và đặc điểm của Map khi thay value.
5. [Java SE 17 – Map.putIfAbsent và Map.merge](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): lựa chọn đại diện dựa trên khóa và merge policy.
6. [Java SE 17 – LinkedHashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html): loại trùng theo equality và duy trì insertion order.
7. [Java SE 17 – List interface](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): List cho phép duplicate, `List.copyOf` cho snapshot unmodifiable có thứ tự.
8. [JEP 286 – Local-Variable Type Inference](https://openjdk.org/jeps/286): `var` từ Java 10, hữu ích để hiểu type inference trong các ví dụ.

**Kết luận:** `Set.copyOf` đảm bảo **loại trùng theo equality và trả Set không thể sửa cấu trúc**, nhưng **không đảm bảo đại diện nào trong nhóm trùng được giữ**. Khi payload của đại diện ảnh hưởng nghiệp vụ, hãy viết chính sách chọn theo key/priority rõ ràng **trước khi** tạo snapshot. Nếu thứ tự kết quả cũng là yêu cầu, ưu tiên `List.copyOf` sau bước chọn đại diện hoặc sắp xếp kết quả; đừng dựa vào iteration order của `Set.copyOf`.
