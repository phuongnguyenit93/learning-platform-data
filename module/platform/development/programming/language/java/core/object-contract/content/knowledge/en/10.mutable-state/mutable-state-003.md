# Thay đổi phần tử trong HashSet và khả năng xuất hiện giá trị trùng

## 1. Hiện tượng: phần tử không còn giữ nguyên điều kiện bằng nhau

Trong Java, `HashSet<E>` thực hiện giao diện `Set<E>` và dùng `equals(Object)` cùng `hashCode()` để kiểm tra phần tử đã có khi thực hiện các thao tác như `add` và `contains`. Với những phần tử có trạng thái xác định equality ổn định, `add(e)` không thêm thêm một phần tử thứ hai bằng `e`.

Nhưng `HashSet` lưu **tham chiếu đến đối tượng**. Khi phần tử là object mutable, việc gọi setter hoặc sửa object lồng nhau có thể thay đổi điều kiện xác định bằng nhau, trong khi set không tự nhận thông báo để rà soát và xây dựng lại cấu trúc nội bộ.

Đặc tả `java.util.Set` nhấn mạnh: **hành vi của set không được xác định khi giá trị của một đối tượng bị thay đổi theo cách tác động đến các phép so sánh `equals` trong lúc đối tượng còn là phần tử của set**.

Hậu quả dễ gây nhầm:

- Hai phần tử lúc thêm vào là khác nhau nhưng sau đó trở thành **bằng nhau** theo `equals` mà `size()` vẫn không đổi.
- `contains` hoặc `remove` có thể không tìm thấy phần tử đã được thêm từ trước.
- Thao tác `add` tiếp theo có thể tạo cảm giác xuất hiện phần tử trùng.
- Các thao tác nghiệp vụ dựa vào số lượng phần tử duy nhất có thể trả kết quả sai so với ý nghĩa hiện tại của dữ liệu.

Đây **không phải lỗi của `HashSet`** nếu object bị thay đổi trái điều kiện ổn định mà cấu trúc dữ liệu dựa vào. Đúng hơn, người sử dụng đã không bảo đảm một giả định quan trọng khi lưu phần tử trong set.

Ngược lại, việc sửa một trường **không tham gia** equality và hash, như ghi chú hiển thị khi ID xác định equality được giữ bất biến, không gây lỗi loại này.

## 2. Liên hệ với hợp đồng Object

Khi override `equals` và `hashCode`, class phải bảo đảm:

1. `equals` có tính phản xạ, đối xứng, bắc cầu; kết quả nhất quán khi dữ liệu được dùng để so sánh không thay đổi; với đối tượng khác `null` thì so với `null` trả `false`.
2. Nếu `a.equals(b)` trả `true` thì `a.hashCode() == b.hashCode()` phải đúng.
3. Nếu `a.equals(b)` trả `false`, hai mã băm **được phép trùng**; va chạm không làm sai contract.
4. Trong cùng một lần thực thi, `hashCode()` phải ổn định nếu những thông tin tham gia phép so sánh equality không đổi.

Hợp đồng số (2) được viết:

`a.equals(b) ⇒ a.hashCode() == b.hashCode()`

Chiều ngược lại **không bắt buộc**: cùng hash không chứng minh hai phần tử bằng nhau.

Một object có thể thay đổi `id`, sau đó `equals` và `hashCode` thay đổi theo `id` nhưng vẫn nhất quán với nhau. Bản thân class chưa chắc vi phạm hợp đồng `Object`. Lỗi xuất hiện khi object này **đang nằm trong `HashSet`**, vì cấu trúc dữ liệu đã được xây trên quan hệ equality/hash trước lúc thay đổi.

## 3. Ví dụ Java 17 chạy được: hai phần tử trở thành trùng nhau

Ví dụ dưới đây so sánh `MutableItem` theo `id`; `label` chỉ phục vụ hiển thị và không tham gia equality.

```java
import java.util.HashSet;
import java.util.Set;

public class HashSetMutationDemo {
    static final class MutableItem {
        private int id;
        private String label;

        MutableItem(int id, String label) {
            this.id = id;
            this.label = label;
        }

        void changeId(int newId) {
            id = newId;
        }

        void changeLabel(String newLabel) {
            label = newLabel;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof MutableItem that)) {
                return false;
            }
            return id == that.id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    public static void main(String[] args) {
        MutableItem first = new MutableItem(101, "Đầu");
        MutableItem second = new MutableItem(202, "Hai");

        Set<MutableItem> items = new HashSet<>();
        System.out.println(items.add(first));
        System.out.println(items.add(second));
        System.out.println(items.size());
        System.out.println(first.equals(second));

        // Sửa trạng thái equality khi first còn trong set.
        first.changeId(202);

        System.out.println(first.equals(second));
        System.out.println(items.size());

        // Đếm bằng duyệt tuần tự, không phụ thuộc vào bucket hash.
        long equalNow = items.stream()
                .filter(item -> item.equals(second))
                .count();
        System.out.println(equalNow);

        // Chỉ sửa mô tả; equality và hash không dùng trường label.
        first.changeLabel("Đổi mô tả");
        System.out.println(first.equals(second));
    }
}
```

Lưu tệp `HashSetMutationDemo.java` bằng UTF-8, biên dịch và chạy:

```bash
javac -encoding UTF-8 HashSetMutationDemo.java
java HashSetMutationDemo
```

Đầu ra:

```text
true
true
2
false
true
2
2
true
```

Diễn giải:

- Ban đầu `first.id = 101`, `second.id = 202`: hai phần tử khác nhau. Hai lần `add` đều trả `true`; set có 2 phần tử và `first.equals(second)` là `false`.
- Gán `first.id = 202` làm `first.equals(second)` chuyển sang `true`. Lúc này hai object khác tham chiếu nhưng bằng nhau theo quy tắc nghiệp vụ đang được class định nghĩa.
- `items.size()` vẫn bằng `2` vì thay đổi trường của phần tử không tự gọi `remove`/`add` trên set.
- `stream().filter(...)` nhìn lần lượt hai phần tử còn trong set và đếm được `2` phần tử hiện cùng `id`. Không có giả định về thứ tự duyệt hay cách phân bổ bucket.
- Đổi `label` không ảnh hưởng `equals`, vì `label` không được dùng để so sánh.

Đây là câu trả lời cụ thể cho việc **một `HashSet` có thể chứa hai phần tử hiện bằng nhau**: chúng đã được thêm khi còn khác nhau và chỉ trở thành bằng nhau sau mutation. Không có lần `add` nào trong ví dụ được gọi với hai đối tượng đang bằng nhau tại thời điểm thêm.

## 4. Vì sao HashSet không tự sửa lại khi ID thay đổi?

Ở các triển khai thường gặp, `HashSet` dùng cấu trúc hash nội bộ để xác định nơi lưu và tra cứu phần tử. Khi object được đưa vào, mã băm hiện tại của nó được dùng để tổ chức việc tra cứu. Nếu trường tạo nên hash thay đổi, mã băm mới có thể dẫn đường tìm kiếm đến vùng khác so với nơi đối tượng đang được giữ.

Cơ chế này giúp hiểu tại sao một phần tử bị sửa có thể bị xem như “mất” khi gọi `contains` hoặc `remove`. Tuy nhiên, **không có kết quả cố định áp dụng cho mọi phiên bản và trạng thái**, vì đặc tả `Set` đã không quy định hành vi sau khi phần tử bị thay đổi theo cách ảnh hưởng equality.

Ví dụ minh họa (đoạn sau đặt trong phương thức có định nghĩa `MutableItem` ở trên):

```java
Set<MutableItem> set = new HashSet<>();
MutableItem item = new MutableItem(1, "Một");
set.add(item);

item.changeId(2);

boolean found = set.contains(item);
boolean removed = set.remove(item);
```

Không nên ghi một stdout khẳng định `found` hoặc `removed` **luôn** là `false`. Kết quả có thể phụ thuộc vào giá trị hash, va chạm và chi tiết triển khai. Điều cần học là: **sau mutation ảnh hưởng equality, không còn cơ sở tin vào việc tra cứu và xóa đúng như lúc khóa còn ổn định**.

Tương tự, nếu sau đó gọi:

```java
// Vẫn là đoạn minh họa trong một phương thức.
set.add(new MutableItem(2, "Hai"));
```

Tùy việc phần tử cũ còn được tìm thấy bằng hash hiện tại hay không, lần thêm có thể phát hiện đối tượng bằng nhau hoặc không. Không có một giá trị trả về chung được cam kết khi đã vi phạm điều kiện giữ ổn định đối tượng phần tử.

## 5. Phân biệt mutation với hash collision

Hai hiện tượng này khác nhau về bản chất:

| Hiện tượng | Ý nghĩa | Có tự làm sai contract không? |
| --- | --- | --- |
| Hai object khác nhau có cùng `hashCode` nhưng `equals` trả `false` | Va chạm hash | **Không**. `HashSet` xử lý bằng equality. |
| Hai object `equals == true` nhưng mã băm khác nhau | Hai phương thức bất nhất | **Có**, vi phạm `Object` contract. |
| Một object đã được thêm rồi thay đổi trường tham gia equality/hash | Thay đổi điều kiện tra cứu của phần tử đang lưu | **Không được đặc tả** bởi `Set`; không dùng như thao tác an toàn. |
| Hai object được thêm khi khác nhau, sau đó một object sửa để bằng object kia | Hai tham chiếu hiện cùng equality vẫn có thể nằm trong set | **Có thể xảy ra** vì set không tự tái kiểm tra. |

Ngay cả class cố ý trả mã băm hằng số `1` cho mọi đối tượng cũng có thể gặp tình huống hai object đã được thêm khi khác nhau rồi trở thành bằng nhau. Hash code hằng không giúp set tự phát hiện thay đổi của `equals`. Sự ổn định của **toàn bộ quan hệ equality** mới là điểm then chốt.

## 6. Trường nào được phép thay đổi?

Giả sử class `Product` định nghĩa “cùng sản phẩm” bằng `productId`:

| Field | Mục đích | Dùng trong equality/hash? | Ảnh hưởng khi sửa trong set |
| --- | --- | --- | --- |
| `productId` | Định danh sản phẩm | Có | Nguy hiểm nếu sửa |
| `displayName` | Tên hiển thị | Không | Không đổi equality/hash của mô hình này |
| `description` | Mô tả | Không | Không đổi equality/hash của mô hình này |
| `cachedLabel` | Kết quả hiển thị đã tính | Không | Có thể làm mới cache mà không đổi equality |
| `quantity` | Số lượng tồn kho | Không, nếu identity chỉ theo ID | Không đổi identity; vẫn có nghĩa vụ kiểm soát logic tồn kho |

Bảng trên chỉ phù hợp khi business contract đã thực sự xác định equality theo `productId`. Với một value object `OrderLine(productId, quantity, price)`, `quantity` hoặc `price` có thể là thành phần quan trọng của equality; khi ấy sửa quantity/price sẽ làm thay đổi điều kiện nhận biết trùng.

Một trường khai báo `final` chưa chắc đảm bảo object bất biến sâu. Ví dụ `final List<String> tags` chỉ ngăn gán lại tham chiếu danh sách, **không ngăn thay đổi phần tử bên trong danh sách**. Nếu nội dung danh sách tham gia `equals`/`hashCode`, object vẫn có thể có hash thay đổi sau khi chèn vào set.

Tương tự, annotation, từ khóa `transient` hoặc việc trường có setter hay không không tự quyết định trường ấy có thuộc equality. Phải dựa trên chính logic `equals`/`hashCode` và ngữ nghĩa của mô hình.

## 7. Cách an toàn nhất: dùng khóa bất biến

Đối với dữ liệu biểu diễn khóa của một set, hãy ưu tiên kiểu bất biến. Trong Java 17, `record` với các component nguyên thủy là một lựa chọn gọn, dễ hiểu:

```java
import java.util.HashSet;
import java.util.Set;

public class ImmutableKeyDemo {
    record ItemKey(int id) {}

    public static void main(String[] args) {
        Set<ItemKey> ids = new HashSet<>();
        System.out.println(ids.add(new ItemKey(101)));
        System.out.println(ids.add(new ItemKey(101)));
        System.out.println(ids.size());
        System.out.println(ids.contains(new ItemKey(101)));
    }
}
```

Lưu `ImmutableKeyDemo.java` rồi chạy:

```bash
javac ImmutableKeyDemo.java
java ImmutableKeyDemo
```

Kết quả:

```text
true
false
1
true
```

Vì component `id` là `int` và record không cho thay thế component sau khi tạo, việc dùng `ItemKey(101)` làm phần tử không bị biến thành `ItemKey(202)` qua setter. Các phương thức `equals`/`hashCode` của record dựa trên component, nên lần `add` thứ hai được nhận diện là giá trị đã tồn tại.

Nếu cần “đổi khóa” từ 101 thành 202, hãy biểu diễn bằng một thao tác ở mức collection:

```java
// Đoạn minh họa đặt trong phương thức có biến Set<ItemKey> ids.
boolean removed = ids.remove(new ItemKey(101));
if (removed) {
    boolean added = ids.add(new ItemKey(202));
    if (!added) {
        // Xử lý xung đột: khóa 202 đã tồn tại.
    }
}
```

**Cần xử lý xung đột nghiệp vụ:** nếu khóa mới đã tồn tại thì phải quyết định từ chối, gộp dữ liệu, thay thế hay phục hồi khóa cũ. Hai câu lệnh `remove` và `add` không mặc nhiên là một transaction nguyên tử trong chương trình nhiều luồng.

Có thể áp dụng lối thiết kế khác: lưu `Set<Id>` thay cho `Set<MutableEntity>` và duy trì bảng thông tin thực thể riêng. Cách này giữ khóa trong set ổn định, còn metadata mutable có vòng đời riêng.

## 8. Nếu buộc phải sửa object đang nằm trong set

Một hướng chỉ khả thi khi bạn kiểm soát toàn bộ vòng đời là:

1. **Xóa phần tử khỏi set khi trường equality/hash vẫn còn ở trạng thái cũ**.
2. Thay đổi trạng thái sau khi phần tử đã được xóa thành công.
3. Thêm lại bằng trạng thái mới.
4. Kiểm tra kết quả `add` và xử lý nếu đã có phần tử khác bằng khóa mới.

Ví dụ tư duy:

```java
// Chỉ an toàn nếu việc xóa diễn ra TRƯỚC khi sửa khóa.
if (set.remove(item)) {
    item.changeId(2);
    boolean added = set.add(item);
    // Nếu added == false: phải có chính sách cho trường hợp trùng.
}
```

Đoạn này không tự giải quyết vấn đề khi có nhiều luồng cùng thao tác; toàn bộ quy trình phải được đồng bộ hóa hoặc bảo vệ bằng cơ chế giao dịch theo yêu cầu hệ thống. Nếu việc thêm thất bại và phải rollback, cần giữ thông tin về trạng thái cũ để khôi phục có kiểm soát.

**Không** ưu tiên kỹ thuật “sửa trước, rồi gọi `remove`”: khi hash đã đổi, remove có thể không tìm được phần tử cũ. Nếu đã xảy ra lỗi, quy trình xử lý khác với một lần thay đổi bình thường.

## 9. Khôi phục một HashSet có phần tử đã thay đổi

Nếu đã có dữ liệu ở trạng thái không còn đáp ứng tính duy nhất theo equality hiện tại:

1. Ngăn hoặc phối hợp các thao tác thay đổi đồng thời trong thời gian khắc phục.
2. Duyệt các phần tử thực tế và thu thập thông tin cần giữ; không chỉ dùng `contains` để kết luận một phần tử có/không.
3. Xác định cặp/nhóm phần tử hiện bằng nhau và cách giải quyết xung đột: giữ đối tượng nào, hợp nhất dữ liệu ra sao, có cần báo lỗi nghiệp vụ không.
4. Tạo một cấu trúc mới bằng các khóa hoặc value object bất biến sau khi xử lý trùng.
5. Thay thế tham chiếu đến cấu trúc cũ theo quy trình kiểm soát; thêm bảo đảm ngăn sửa khóa lần nữa.

Có thể tạo `new HashSet<>(oldSet)`, nhưng nó sẽ loại bỏ phần tử bị xem là trùng theo equality hiện tại. Nếu những phần tử ấy chứa thông tin mô tả hoặc dữ liệu khác nhau, việc loại bỏ có thể khiến mất dữ liệu có ý nghĩa. Vì vậy **dựng lại collection sau khi đã có chính sách giải quyết trùng**, không mặc nhiên xem copy constructor là công cụ sửa mọi vấn đề.

Không dựa vào việc tạm đổi ID về giá trị cũ để `remove` rồi đổi trở lại như một giải pháp tổng quát. Bạn có thể không biết giá trị cũ; các xung đột đã xuất hiện cũng có thể khó phục hồi.

## 10. Unmodifiable set có ngăn vấn đề không?

Không tự động.

`Collections.unmodifiableSet(source)` trả về một view không cho thêm/xóa qua chính view ấy. Nếu mã khác vẫn giữ tham chiếu đến phần tử mutable hoặc đến set nguồn, dữ liệu và các phần tử vẫn có thể thay đổi.

`Set.copyOf(source)` tạo một set không cho chỉnh sửa cấu trúc qua API của nó, nhưng **không deep copy** mọi phần tử. Một `MutableItem` được đặt trong set ấy vẫn là cùng đối tượng mutable nếu có nơi khác giữ tham chiếu. Đổi trường equality vẫn có thể làm hỏng các giả định về phần tử ổn định.

Phân biệt:

- **Unmodifiable collection:** người dùng không sửa cấu trúc collection qua giao diện được trả về.
- **Immutable element:** dữ liệu định nghĩa equality/hash của phần tử không thay đổi.
- **Stable set semantics:** đòi hỏi phần tử giữ điều kiện equality/hash đúng trong suốt thời gian thuộc set.

Một record có component là `List` mutable cũng không tự trở thành immutable sâu. Có thể dùng defensive copy thích hợp như `List.copyOf` trong constructor cho thành phần cần giữ ổn định.

## 11. Iterator, fail-fast và đa luồng

Thay đổi một trường của đối tượng được tham chiếu trong set thường không phải một thao tác thay đổi **cấu trúc collection**. Vì vậy không thể trông chờ `ConcurrentModificationException` để phát hiện mọi trường hợp đổi `id` hoặc `hashCode`. Cơ chế fail-fast của iterator vốn cũng chỉ là best-effort.

Nếu nhiều luồng cùng sửa, tra cứu hoặc duyệt các object mutable, còn cần thiết kế đồng bộ hóa và bảo đảm hiển thị bộ nhớ. Một collection concurrent có thể bảo vệ thao tác cấu trúc riêng của nó, nhưng **không tự khiến dữ liệu định nghĩa equality của phần tử trở nên ổn định**.

Một entity ORM có ID gán sau khi lưu cũng cần cân nhắc kỹ. Nếu `equals`/`hashCode` dựa vào ID từ `null` thành giá trị thực sau khi đối tượng đã được cho vào set, thay đổi vòng đời ấy có thể ảnh hưởng đến chính những giả định đang học. Không áp dụng quy tắc “dùng ID” một cách máy móc mà bỏ qua thời điểm ID ổn định và semantics của ORM.

## 12. Checklist trước khi chọn class làm phần tử HashSet

- **Định nghĩa equality:** hai phần tử bằng nhau khi nào theo miền nghiệp vụ?
- **Tương thích hash:** mọi cặp bằng nhau có cùng `hashCode` không?
- **Trạng thái ổn định:** trường trực tiếp hoặc gián tiếp được dùng trong equality/hash có thể đổi không?
- **Tham chiếu lồng nhau:** danh sách, mảng, object con trong khóa có thể thay đổi nội dung không?
- **Vòng đời:** có setter hoặc sự kiện tự động sửa ID khi object vẫn thuộc set không?
- **Phương án thay đổi:** nếu phải đổi khóa, đã có quy trình remove trước, thay đổi sau, add lại và xử lý xung đột chưa?
- **Chế độ kiểm thử:** đã kiểm tra kịch bản hai phần tử khác nhau trở thành bằng nhau, mà không dựa vào thứ tự bucket hoặc giá trị `contains` chưa?

## 13. Câu hỏi tự luyện

**Câu 1.** Hai phần tử được thêm khi có ID lần lượt 1 và 2. Sau đó ID của phần tử thứ nhất bị đổi thành 2. Set có tự giảm `size()` còn 1 không?

**Đáp án:** Không có cơ chế bắt buộc kiểm tra lại equality sau khi trường của phần tử bị sửa. Trong ví dụ Java 17 đã chạy, set giữ 2 tham chiếu mặc dù hai object trở thành bằng nhau theo `equals`.

**Câu 2.** Hai đối tượng có cùng mã băm nhưng `equals` trả `false`. `HashSet` có được giữ cả hai không?

**Đáp án:** Có. Va chạm hash được cho phép; trong trạng thái hợp lệ, so sánh equality giúp nhận diện hai phần tử khác nhau.

**Câu 3.** Một class so sánh theo `immutableId` nhưng cho sửa `displayName`. Việc thay tên khi đối tượng thuộc set có gây lỗi đang bàn không?

**Đáp án:** Không, miễn là tên không tham gia trực tiếp hay gián tiếp vào equality/hash. Các vấn đề nghiệp vụ và concurrency vẫn phải xử lý riêng.

**Câu 4.** Nếu `hashCode` luôn trả `1` thì các phần tử có thể trở thành trùng sau mutation không?

**Đáp án:** Có. Hash hằng số không làm set tự đánh giá lại equality. Hai phần tử có thể chuyển từ khác nhau sang bằng nhau sau khi trường dùng trong `equals` đổi.

**Câu 5.** Vì sao không nên viết bài test yêu cầu `set.contains(mutatedItem)` luôn `false`?

**Đáp án:** Vì `Set` không đặc tả hành vi khi phần tử bị sửa theo cách ảnh hưởng equality trong thời gian thuộc set. Trạng thái và implementation có thể cho các kết quả khác nhau. Cần kiểm tra việc **ngăn thay đổi khóa**, không coi hậu quả riêng của một JVM là contract.

## 14. Ghi nhớ

1. `HashSet` xác định tính trùng lặp theo `equals` và `hashCode` khi thao tác với các phần tử.
2. **Không thay đổi dữ liệu tham gia equality/hash khi phần tử đang thuộc set**. Đặc tả `Set` không bảo đảm kết quả cho tình huống này.
3. Hai object lúc thêm khác nhau có thể **trở thành bằng nhau** sau mutation; set vẫn có thể giữ hai tham chiếu, như ví dụ cụ thể.
4. `contains`, `remove` hoặc `add` sau mutation không còn là bằng chứng đáng tin cho tính duy nhất.
5. Ưu tiên khóa bất biến; nếu phải đổi khóa, quản lý remove/modify/add cùng chính sách giải quyết xung đột.
6. Unmodifiable set không làm các element mutable trở thành immutable; `final` không tự bảo đảm bất biến sâu.

Tài liệu đối chiếu: [`Set` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html), [`HashSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html), [`Object.equals/hashCode`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html) và [`Collections.unmodifiableSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableSet(java.util.Set)).
