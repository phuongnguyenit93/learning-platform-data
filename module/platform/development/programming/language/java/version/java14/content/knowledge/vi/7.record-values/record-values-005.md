# Đối tượng thành phần thay đổi sau khi tạo record

## 1. Record giữ tham chiếu cố định, không tự đóng băng đối tượng được tham chiếu

Một `record` là class dùng để mô tả tập giá trị qua các **record components**. Từ Java 16, record là tính năng ổn định; các ví dụ trong bài chạy với **Java 17+**. Record được giới thiệu trong lộ trình ngôn ngữ trước đó, nhưng chúng ta chỉ sử dụng hành vi đã chuẩn hóa và vẫn còn áp dụng hiện nay.

Xét khai báo:

~~~java
record Cart(List<String> items) {}
~~~

Compiler cung cấp field `private final List<String> items`, accessor `public List<String> items()`, canonical constructor và các phương thức `equals`, `hashCode`, `toString`. Từ khóa **`final` chỉ áp dụng cho field lưu tham chiếu**, nghĩa là một khi khởi tạo xong không thể gán field đó sang một `List` khác. Nó **không** khiến đối tượng `List` đang được trỏ đến trở thành bất biến.

Cần phân biệt ba mức:

| Mức | Record bảo đảm mặc định? | Ý nghĩa |
| --- | --- | --- |
| Không thể gán lại field component sau xây dựng | **Có** | Field của record là `private final` |
| Không thể thay đổi trạng thái của đối tượng nằm trong field | **Không** | `ArrayList`, mảng, `StringBuilder`, đối tượng nghiệp vụ mutable vẫn thay đổi được |
| Không thể thay đổi đối tượng lồng sâu bên trong một collection | **Không** | Dù collection không cho `add/remove`, chính các phần tử mutable vẫn đổi được |

Ví dụ, field `List<String> items` không thể được gán lại từ bên trong record sau khi xây dựng; nhưng lệnh `cart.items().add("B")` vẫn chạy nếu `items()` trả về một `ArrayList` mutable. Ngược lại, `String` và các kiểu dữ liệu bất biến khác vốn không có phép sửa nội dung từ bên ngoài. Khi cần một **value object ổn định**, ta phải lựa chọn kiểu component phù hợp và chủ động phòng vệ với dữ liệu mutable.

Bài học trung tâm: **record có tính bất biến nông (shallow immutability) ở các tham chiếu component, chứ không mặc nhiên có tính bất biến sâu (deep immutability) của toàn bộ đồ thị đối tượng.**

## 2. Ba đường khiến trạng thái “của record” quan sát được thay đổi

Với một record chứa tham chiếu đến đối tượng mutable, thay đổi có thể đến từ nhiều nơi:

1. **Alias từ trước khi tạo:** code gọi constructor vẫn giữ biến trỏ vào chính đối tượng được truyền, rồi sửa đối tượng đó. Vì record mặc định lưu nguyên tham chiếu, thay đổi xuất hiện khi đọc lại component.
2. **Accessor làm lộ tham chiếu:** accessor được sinh mặc định trả đúng tham chiếu đang lưu. Người gọi lấy nó rồi `add`, `remove`, sửa mảng hoặc gọi một phương thức thay đổi trạng thái.
3. **Alias của phần tử lồng bên trong:** ngay cả khi record dùng một `List` không thể thêm/bớt phần tử, một phần tử có thể là đối tượng mutable và bị sửa qua tham chiếu ở nơi khác.

Minh họa sơ đồ alias đơn giản:

~~~text
Biến của người gọi: original ─────┐
                                   ├──> [ ArrayList mutable ]
Record: cart.items (final) ────────┘

original.add("S2")  ───────────────> thay đổi cùng một ArrayList
cart.items()        ───────────────> đọc thấy ["S1", "S2"]
~~~

Chỉ một **đối tượng List** được chia sẻ giữa hai tham chiếu; record không tự sinh bản sao trong canonical constructor mặc định. Với component kiểu mảng như `int[]`, vấn đề cũng tương tự: field `final int[]` giữ tham chiếu cố định, nhưng các phần tử trong mảng vẫn thay đổi bằng `array[i] = value`.

## 3. Ví dụ Java 17+: thay đổi qua alias đầu vào và accessor

Tạo tệp **`MutableRecordDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class MutableRecordDemo {
    record Cart(List<String> lines) {}
    record Samples(int[] values) {}

    public static void main(String[] args) {
        List<String> original = new ArrayList<>(List.of("S1"));
        Cart cart = new Cart(original);
        Cart baseline = new Cart(List.of("S1"));

        int initialHash = cart.hashCode();
        System.out.println("equalBefore=" + cart.equals(baseline));

        original.add("S2");
        System.out.println("viaOriginal=" + cart.lines());
        System.out.println("equalAfter=" + cart.equals(baseline));
        System.out.println("hashChanged="
                + (initialHash != cart.hashCode()));

        cart.lines().add("S3");
        System.out.println("viaAccessor=" + original);

        int[] numbers = {1, 2};
        Samples samples = new Samples(numbers);
        System.out.println("arrayBefore="
                + Arrays.toString(samples.values()));
        numbers[0] = 7;
        System.out.println("arrayAfter="
                + Arrays.toString(samples.values()));
        System.out.println("arrayEquals="
                + samples.equals(new Samples(new int[]{7, 2})));
    }
}
~~~

Biên dịch bằng JDK 17 trở lên. Cờ `--release 17` đảm bảo ví dụ chỉ dùng API và cú pháp của Java 17:

~~~bash
javac --release 17 -encoding UTF-8 MutableRecordDemo.java
java MutableRecordDemo
~~~

Stdout đã kiểm tra khi chạy ví dụ:

~~~text
equalBefore=true
viaOriginal=[S1, S2]
equalAfter=false
hashChanged=true
viaAccessor=[S1, S2, S3]
arrayBefore=[1, 2]
arrayAfter=[7, 2]
arrayEquals=false
~~~

Diễn giải theo đúng thứ tự:

- `cart` và `baseline` ban đầu đều chứa danh sách với `"S1"`. `List.equals` so sánh phần tử theo thứ tự, nên `cart.equals(baseline)` là `true`.
- Sau `original.add("S2")`, `cart.lines()` thấy `[S1, S2]` vì cùng giữ một `ArrayList`. Lúc này `cart.equals(baseline)` là `false` dù không tạo record mới và không gán lại field nào.
- `hashChanged=true` là kết quả của **dữ liệu mẫu và JDK đã dùng để kiểm thử**; không nên phát biểu rằng mọi thay đổi đều bắt buộc tạo hash mới vì có thể có va chạm hash. Điều quan trọng là `hashCode()` của record dựa vào giá trị component và **có thể biến đổi** khi component mutable đổi.
- `cart.lines().add("S3")` chứng minh accessor sinh mặc định làm lộ tham chiếu mutable; biến `original` cũng thấy dữ liệu mới.
- Với `Samples`, sửa `numbers[0]` làm mảng trong record đổi từ `[1, 2]` sang `[7, 2]`.
- Hai record chứa **hai đối tượng mảng khác nhau** nhưng có cùng giá trị phần tử vẫn có `equals == false` khi dùng phương thức tự sinh, vì `int[]` không cung cấp `equals` so sánh theo nội dung. Quy tắc này khác với `List.equals`.

**Không thể suy ra “record là bất biến” chỉ vì dòng khai báo record không chứa setter.** Đôi khi thay đổi đến từ biến cũ; đôi khi chính accessor cho phép sửa trực tiếp; đôi khi phần tử bên trong thay đổi.

## 4. Vì sao `equals`, `hashCode` và `toString` có thể bị ảnh hưởng?

Các phương thức được compiler tạo cho record lấy dữ liệu từ **component fields** để xác định giá trị record:

- **`equals(Object)`:** so sánh các giá trị component. Với component kiểu tham chiếu, logic tương ứng với `equals` của kiểu tham chiếu, xử lý `null` phù hợp. Nếu `List` đổi phần tử thì kết quả so sánh record có thể đổi.
- **`hashCode()`:** kết hợp hash của các component. Nếu component như `ArrayList` có hash phụ thuộc nội dung, hash của record có thể đổi theo nội dung. Thuật toán kết hợp cụ thể do JDK quyết định; không được dựa vào một công thức hash cố định của record.
- **`toString()`:** tạo biểu diễn từ tên record và các component. Khi một component là `List` mutable, biểu diễn chuỗi của record có thể khác trước và sau thay đổi.

Đặc biệt, **record không tự làm `equals` của mảng thành so sánh từng phần tử**:

~~~java
record Numbers(int[] values) {}

Numbers x = new Numbers(new int[]{1, 2});
Numbers y = new Numbers(new int[]{1, 2});
System.out.println(x.equals(y)); // false: hai tham chiếu mảng khác nhau
~~~

Đây là đoạn **minh họa trong phương thức** với kiểu record khai báo trong phạm vi phù hợp; nó không phải tệp có `main` độc lập. Dùng `Arrays.equals` cho một chiều mảng nguyên thủy, `Arrays.deepEquals` cho những mảng lồng thích hợp, nếu ngữ nghĩa nghiệp vụ thực sự cần so sánh **giá trị phần tử**.

### Rủi ro khi record làm khóa của `HashMap` hoặc phần tử của `HashSet`

Các cấu trúc dựa vào hash kỳ vọng `equals` và `hashCode` của key/element **ổn định** trong thời gian đối tượng được lưu. Nếu record có component `List` mutable, thêm/bớt phần tử sau khi đưa record vào `HashMap` hoặc `HashSet` có thể làm hash thay đổi, khiến tra cứu hoặc xóa bằng key ban đầu không hoạt động như mong muốn. Không nên đưa record chứa state thay đổi vào vai trò khóa theo giá trị.

Tuy nhiên, **không phải mọi mutation đều làm hash thay đổi** và cũng không được dựa vào bất kỳ giá trị hash cụ thể nào làm hợp đồng nghiệp vụ. Rủi ro nằm ở chính việc giá trị/hash có thể thay đổi theo thời gian.

## 5. Tạo snapshot an toàn cho `List<String>`

Nếu một record biểu diễn dữ liệu tại **thời điểm khởi tạo**, dùng **defensive copy** khi đưa collection vào record. Cách gọn, rõ với `List<String>` là:

~~~java
record SafeOrder(List<String> skus) {
    SafeOrder {
        skus = List.copyOf(skus);
    }
}
~~~

Đây là **compact canonical constructor**: biến `skus` trong thân constructor là tham số. Gán lại tham số thành bản snapshot bất biến; sau khi thân constructor kết thúc, Java tự gán giá trị tham số cuối cùng vào field `private final` tương ứng. Với compact constructor, **không được tự gán `this.skus = ...`**.

`List.copyOf(skus)` có các đặc điểm:

1. Tạo hoặc tái sử dụng một **List không cho sửa cấu trúc** chứa các phần tử theo thứ tự hiện có; các thao tác thêm, xóa, thay thế phần tử đều bị từ chối.
2. Sửa **collection đầu vào** sau đó không làm thay đổi tập phần tử trong `List` kết quả.
3. Nếu đầu vào đã là một `List` không thể sửa thích hợp, implementation có thể **tái sử dụng cùng instance**; đừng yêu cầu danh tính đối tượng mới, hãy quan tâm đến hợp đồng snapshot.
4. `List.copyOf` **không sao chép sâu từng phần tử**. Nó chỉ bảo vệ cấu trúc collection. Với `List<String>`, do `String` là kiểu bất biến, cách này thường đủ để dữ liệu giữ nguyên.
5. `List.copyOf(null)` hoặc một đầu vào chứa phần tử `null` sẽ ném `NullPointerException`. Hãy quyết định rõ chính sách về giá trị null; đừng đưa phần tử null vào trong khi dùng `List.copyOf`.

Không nhầm `List.copyOf(source)` với `Collections.unmodifiableList(source)`: cách sau chỉ tạo **view** không cho sửa qua view, nhưng nếu `source` mutable bị sửa ở nơi khác thì view vẫn phản ánh thay đổi. `List.copyOf` là lựa chọn đơn giản để tạo snapshot cấu trúc độc lập.

## 6. Mảng cần phòng vệ ở cả constructor và accessor

Không có `List.copyOf` cho mảng nguyên thủy. Với `int[]` một chiều, dùng `clone()` hoặc `Arrays.copyOf(...)` để tách mảng khỏi đầu vào và tách mảng khi trả ra ngoài. Nếu chỉ clone **trong constructor**, accessor mặc định vẫn trả mảng nội bộ và người gọi sửa được; nếu chỉ clone **trong accessor**, đầu vào còn giữ quyền thay đổi mảng nội bộ. Vì vậy phải xét **cả hai chiều**.

Trường hợp record dùng mảng để biểu diễn một **giá trị theo nội dung**, còn cần làm rõ `equals`, `hashCode` và `toString`. Chỉ defensive copy mảng **không** tự biến `equals` mặc định thành so sánh nội dung.

Ví dụ đầy đủ sau minh họa hai trường hợp. Tạo tệp **`DefensiveRecordDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class DefensiveRecordDemo {
    record SafeOrder(List<String> skus) {
        SafeOrder {
            skus = List.copyOf(skus);
        }
    }

    record ClonedArray(int[] values) {
        ClonedArray {
            values = values.clone();
        }
        @Override public int[] values() {
            return values.clone();
        }
    }

    record ValueArray(int[] values) {
        ValueArray {
            values = values.clone();
        }
        @Override public int[] values() {
            return values.clone();
        }
        @Override public boolean equals(Object other) {
            return other instanceof ValueArray that
                    && Arrays.equals(values, that.values);
        }
        @Override public int hashCode() {
            return Arrays.hashCode(values);
        }
        @Override public String toString() {
            return "ValueArray[values=" + Arrays.toString(values) + "]";
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("S1"));
        SafeOrder order = new SafeOrder(source);
        source.add("S2");
        System.out.println("snapshot=" + order.skus());
        try {
            order.skus().add("S3");
        } catch (UnsupportedOperationException ex) {
            System.out.println("readonly=UnsupportedOperationException");
        }

        int[] input = {1, 2};
        ValueArray value = new ValueArray(input);
        input[0] = 9;
        System.out.println("afterInputChange=" + Arrays.toString(value.values()));
        int[] exported = value.values();
        exported[1] = 8;
        System.out.println("afterAccessorChange=" + Arrays.toString(value.values()));
        System.out.println("valueCopyEqual="
                + value.equals(new ValueArray(value.values())));
        System.out.println("valueHashEqual="
                + (value.hashCode()
                    == new ValueArray(new int[]{1, 2}).hashCode()));
        System.out.println("value=" + value);

        ClonedArray cloned = new ClonedArray(new int[]{1, 2});
        System.out.println("defaultArrayEqual="
                + cloned.equals(new ClonedArray(cloned.values())));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 DefensiveRecordDemo.java
java DefensiveRecordDemo
~~~

Stdout đã kiểm tra:

~~~text
snapshot=[S1]
readonly=UnsupportedOperationException
afterInputChange=[1, 2]
afterAccessorChange=[1, 2]
valueCopyEqual=true
valueHashEqual=true
value=ValueArray[values=[1, 2]]
defaultArrayEqual=false
~~~

Các mốc quan trọng:

- `SafeOrder` đã giữ snapshot của `[S1]`; `source.add("S2")` không sửa được dữ liệu bên trong record. Gọi `add("S3")` qua accessor ném `UnsupportedOperationException`.
- `ValueArray` clone mảng khi khởi tạo nên sửa `input[0]` không ảnh hưởng. Accessor trả clone nên sửa `exported[1]` cũng không ảnh hưởng.
- `ValueArray.equals` dùng `Arrays.equals`; `hashCode` dùng `Arrays.hashCode` cho cùng ngữ nghĩa giá trị. Vì thế hai record chứa `[1, 2]` được coi bằng nhau và có cùng hash.
- `ValueArray.toString` được viết lại chỉ để hiện phần tử mảng rõ ràng, thay vì biểu diễn mặc định dựa vào `toString()` của mảng.
- `ClonedArray` đã clone hai chiều nhưng **không override `equals`**. Hai bản tạo ra từ các mảng mới cùng nội dung vẫn **khác nhau** với `equals` mặc định. Defensive copy và value equality là hai yêu cầu độc lập.

**Lưu ý:** Với mảng nhiều chiều như `int[][]`, `clone()` ở mảng ngoài chỉ là **bản sao nông**; các mảng con vẫn có thể được chia sẻ. Muốn snapshot sâu hơn, phải sao chép từng mảng con và xác định ngữ nghĩa so sánh nội dung tương ứng. Nếu không cần đặc điểm mảng, hãy cân nhắc dùng `List` gồm các phần tử bất biến để đơn giản hóa hợp đồng.

### Liên hệ với bất biến copy của record

Một nguyên tắc thiết kế được tài liệu `java.lang.Record` nêu là: khi tạo record mới từ các giá trị thu qua accessor của record hiện có, record mới nên bằng record gốc theo `equals`. Với mảng, override accessor để clone nhưng vẫn giữ `equals` mặc định so sánh tham chiếu sẽ **làm mất** đặc tính đó. `ValueArray` giải quyết vấn đề bằng `Arrays.equals` và `Arrays.hashCode`, nhất quán với cách constructor/accessor phòng vệ.

Cũng cần nhớ: phương thức `equals` được sinh mặc định xem **component fields**, không gọi accessor do bạn override. Vì vậy chỉ thay đổi cách accessor trả dữ liệu không đủ để sửa ngữ nghĩa so sánh của record.

## 7. `List.copyOf` vẫn không bảo vệ phần tử mutable lồng bên trong

Đây là lỗi dễ bỏ sót nhất. Một `List` không thể thêm/xóa vẫn có thể chứa những đối tượng mà phương thức của chúng thay đổi trạng thái. Xét một `MutableItem` có setter `rename`:

- `ShallowCatalog` dùng `List.copyOf` để chặn việc sửa cấu trúc collection qua alias.
- Nhưng `MutableItem` có thể được giữ tham chiếu bởi code khác, nên nội dung của phần tử vẫn thay đổi.
- Muốn lưu một snapshot giá trị, hãy **chuyển từng phần tử sang đối tượng bất biến**, rồi mới tạo `List.copyOf`.

Chương trình minh họa đầy đủ. Tạo tệp **`NestedMutationDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class NestedMutationDemo {
    static final class MutableItem {
        private String sku;

        MutableItem(String sku) {
            this.sku = Objects.requireNonNull(sku);
        }

        String sku() {
            return sku;
        }

        void rename(String newSku) {
            sku = Objects.requireNonNull(newSku);
        }
    }

    record ShallowCatalog(List<MutableItem> items) {
        ShallowCatalog {
            items = List.copyOf(items);
        }
    }

    record ItemValue(String sku) {
        ItemValue {
            Objects.requireNonNull(sku, "sku");
        }
    }

    record CapturedCatalog(List<ItemValue> items) {
        CapturedCatalog {
            items = List.copyOf(items);
        }

        static CapturedCatalog capture(List<MutableItem> source) {
            List<ItemValue> snapshots = source.stream()
                    .map(item -> new ItemValue(item.sku()))
                    .toList();
            return new CapturedCatalog(snapshots);
        }
    }

    public static void main(String[] args) {
        MutableItem item = new MutableItem("OLD");
        List<MutableItem> original = new ArrayList<>(List.of(item));

        ShallowCatalog shallow = new ShallowCatalog(original);
        CapturedCatalog captured = CapturedCatalog.capture(original);

        original.clear();
        item.rename("NEW");

        System.out.println("listSize=" + shallow.items().size());
        System.out.println("shallowSku=" + shallow.items().get(0).sku());
        System.out.println("capturedSku=" + captured.items().get(0).sku());
        System.out.println("captured=" + captured);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 NestedMutationDemo.java
java NestedMutationDemo
~~~

Stdout đã kiểm tra:

~~~text
listSize=1
shallowSku=NEW
capturedSku=OLD
captured=CapturedCatalog[items=[ItemValue[sku=OLD]]]
~~~

Giải thích:

1. `original.clear()` không làm danh sách của `shallow` hoặc `captured` mất phần tử; cả hai đã chụp snapshot cấu trúc.
2. `item.rename("NEW")` **vẫn tác động lên phần tử được `ShallowCatalog` giữ** vì `List.copyOf` không clone các phần tử. Kết quả `shallowSku=NEW`.
3. `CapturedCatalog.capture` chuyển dữ liệu từng phần tử sang record `ItemValue(String sku)`. Vì `String` bất biến và `List.copyOf` chặn thay đổi collection, ảnh chụp `OLD` vẫn ổn định.

Đây là **snapshot theo giá trị có chủ đích**, không phải một hàm “deep copy tổng quát” cho mọi đồ thị đối tượng. Nếu một phần tử còn chứa `List`, `Map`, mảng hay đối tượng mutable khác, cần tiếp tục xác định và chụp snapshot ở các mức đó theo hợp đồng dữ liệu.

## 8. Khi nào nên giữ tham chiếu live, khi nào cần snapshot?

Không phải mọi record có component mutable đều là lỗi ngôn ngữ. Java cho phép nó; vấn đề là **ý nghĩa nghiệp vụ**.

| Mục đích | Cách thiết kế nên cân nhắc |
| --- | --- |
| Thể hiện một ảnh chụp trạng thái đơn hàng tại thời điểm tạo | Record chứa số, chuỗi, thời gian bất biến, danh sách đã copy, phần tử bất biến |
| Nhận danh sách từ code bên ngoài nhưng không muốn có thay đổi cấu trúc sau đó | `List.copyOf` khi dữ liệu không chứa `null` và các phần tử phù hợp |
| Nhận mảng nguyên thủy và cần value equality theo phần tử | Clone đầu vào/đầu ra; cân nhắc override `equals`/`hashCode`/`toString` nhất quán |
| Nhận `List<MutableItem>` nhưng muốn ảnh chụp hoàn toàn độc lập | Snapshot từng phần tử sang immutable value object, sau đó copy danh sách |
| Cần mô tả một thực thể thay đổi liên tục theo thời gian, có cập nhật và vòng đời riêng | Thường nên dùng class nghiệp vụ thường, hoặc record chỉ chứa ID/snapshot rõ nghĩa |
| Cần đưa đối tượng vào `HashMap` key hoặc `HashSet` ổn định | Ưu tiên thành phần có `equals`/`hashCode` ổn định và bất biến theo thời gian |

Về **concurrency**, `final` của field record không tự đồng bộ hóa mọi mutation của đối tượng được tham chiếu. Một luồng thêm phần tử vào `ArrayList` trong khi luồng khác đọc qua accessor vẫn gặp các vấn đề thread safety của `ArrayList`; record không thay thế khóa, cấu trúc đồng bộ hoặc cơ chế chia sẻ snapshot an toàn. Khi chụp snapshot từ một nguồn mutable đang bị sửa đồng thời, cũng cần phối hợp đồng bộ hóa ở ranh giới thu thập dữ liệu để đảm bảo snapshot nhất quán.

Về **hiệu năng**, defensive copy có chi phí bộ nhớ và xử lý phụ thuộc kích thước dữ liệu. Không nên bỏ qua copy chỉ vì muốn tiết kiệm khi hợp đồng đòi snapshot; thay vào đó hãy chọn biểu diễn và thời điểm copy thích hợp, chỉ copy những phần mutable thực sự cần cách ly.

## 9. Những lỗi hiểu sai thường gặp

1. **“Record không có setter nên đối tượng bất biến.”** Sai: accessor có thể làm lộ `ArrayList` hoặc mảng mutable; alias đầu vào cũng có thể sửa đối tượng.
2. **“Field `final` khiến mọi phần tử trong mảng trở thành `final`.”** Sai: `final` chỉ ngăn gán lại field tham chiếu, không ngăn `array[i] = ...`.
3. **“`Collections.unmodifiableList(original)` tạo bản sao độc lập.”** Sai: đây là view không sửa được qua view; sửa `original` vẫn có thể thấy qua view.
4. **“`List.copyOf` làm mọi phần tử bất biến.”** Sai: một `MutableItem` bên trong vẫn có thể `rename`; đây là sao chép nông.
5. **“Clone mảng ở constructor là đủ.”** Sai khi accessor trả mảng nội bộ và người gọi còn sửa được qua accessor.
6. **“Override accessor để clone mảng cũng sửa luôn `equals`.”** Sai: `equals` mặc định dựa vào component field và mảng so sánh theo tham chiếu. Muốn value equality theo phần tử cần chủ động thiết kế `equals`/`hashCode` tương ứng.
7. **“Mọi thay đổi dữ liệu đều làm hash khác.”** Không có bảo đảm đó; hash có thể va chạm. Nhưng việc hash **có thể thay đổi** đã đủ để khiến một record không an toàn làm key lâu dài.
8. **“`List.copyOf` cho phép phần tử null.”** Sai: phần tử `null` bị từ chối. Nếu nghiệp vụ cho phép dữ liệu thiếu, cần lựa chọn hợp đồng và cách lưu trữ khác.
9. **“Record tự động an toàn trong đa luồng.”** Sai với component tham chiếu đến cấu trúc mutable không an toàn trong đa luồng.

## 10. Checklist thực hành

Trước khi công khai một record như một giá trị ổn định, hãy trả lời:

- Component nào là primitive hoặc kiểu bất biến (ví dụ `String`, `LocalDate`)? Component nào có trạng thái mutable (mảng, collection, custom mutable class)?
- Có ai giữ **alias của dữ liệu đầu vào** sau khi constructor hoàn tất không? Đã copy ở ranh giới khởi tạo chưa?
- Accessor có trả về chính đối tượng mutable bên trong không? Với mảng cần copy khi đọc; với collection đã snapshot và unmodifiable, có thể trả collection nếu phần tử cũng bất biến.
- Nếu collection chứa phần tử mutable, đã chụp snapshot từng phần tử hay chỉ copy cấu trúc?
- `equals` và `hashCode` có thực sự biểu diễn đúng ngữ nghĩa giá trị không, đặc biệt với mảng? Kết quả có giữ ổn định sau khi đối tượng được dùng làm key/set không?
- Thay đổi ngoài ý muốn có thể ảnh hưởng `toString`, log, cache, so sánh hoặc dữ liệu hiển thị không?
- Nguồn dữ liệu có thể bị sửa đồng thời trong khi copy không, và đã thiết lập cách lấy snapshot nhất quán chưa?

Nếu ý định là **snapshot dữ liệu**, hãy thực thi bất biến đó tại **constructor và ranh giới truy cập**; đừng chỉ dựa vào từ khóa `record`. Nếu ý định là **live reference**, hãy ghi rõ hợp đồng rằng trạng thái quan sát được có thể đổi và tránh giả định đây là một value object ổn định.

## Nguồn Java chính thức

- Java Language Specification, Java SE 27, §8.10 *Record Classes*: field component `private final`, accessor và cơ chế `equals`/`hashCode`/`toString`: https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.10
- Java SE 17 API, `java.lang.Record`: ràng buộc semantic copy, canonical constructor và accessor phòng vệ: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html
- Java SE 17 API, `List.copyOf` và *Unmodifiable Lists*: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)
- Java SE 17 API, `Collection`, *Unmodifiable Collections*: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html
- OpenJDK JEP 395, *Records* (tính năng ổn định từ Java 16): https://openjdk.org/jeps/395