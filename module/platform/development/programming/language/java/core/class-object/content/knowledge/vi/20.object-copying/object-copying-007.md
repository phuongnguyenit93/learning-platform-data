# Chọn cách sao chép theo quyền sở hữu và khả năng thay đổi trong Java

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **object identity**, reference aliasing, assignment, shallow copy, selective deep copy, immutable snapshot và live view.
- Phân tích **ai sở hữu dữ liệu**, **ai có quyền sửa**, **ai cần giữ dữ liệu sau lời gọi**, **dữ liệu có thay đổi theo thời gian không**, để chọn một chiến lược sao chép rõ ràng.
- Biết khi nào **chia sẻ reference** là đúng: thành phần thực sự immutable, một resource được mượn có chủ đích, hoặc dữ liệu live theo contract có quản lý mutation.
- Biết khi nào phải **defensive-copy ở đầu vào**, **đầu ra**, hay **cả hai**: mutable objects đi qua ranh giới API, snapshots cần ổn định, collections có mutable nested elements.
- Dùng copy constructor, factories, `array.clone()`, `Arrays.copyOf`, `new ArrayList<>(source)`, `List.copyOf` và `Map.copyOf` đúng ngữ nghĩa, không nhầm copy container với copy component.
- Phân biệt **transfer ownership theo quy ước** với sự cưỡng chế của ngôn ngữ: Java không có một move-only ownership system đảm bảo mọi aliases cũ bị vô hiệu.
- Thiết kế immutable value objects/records và snapshots đáp ứng equality, hash-key stability, invariants và ownership boundaries.
- Cân nhắc object graphs có chu trình, shared nodes và references tới tài nguyên để quyết định phạm vi copy mà không phá graph semantics.
- Hiểu tác động tới đa luồng: immutable snapshots giúp chia sẻ dữ liệu ổn định; một shallow copy không tách mutable child khỏi threads khác.
- So sánh chi phí copy, structural sharing, copy-on-write, lifetime và tài nguyên; chọn **mức copy tối thiểu nhưng đủ đúng contract**, không chọn “deep copy mọi thứ” theo thói quen.
- Chạy chương trình Java 17+ độc lập, dự đoán stdout và kiểm thử quyết định copy bằng identity/state tests.

## 1. Trước khi copy, phải hỏi: ai sở hữu và ai được sửa?

Trong Java, biến tham chiếu giữ **giá trị reference** tới object. Lệnh:

~~~java
Document second = first;
~~~

**không sao chép Document object**; `second` và `first` cùng tham chiếu một object. Nếu Document mutable, thay đổi qua một reference có thể được nhìn thấy qua reference kia.

Copy chỉ có ích khi đáp ứng một yêu cầu cụ thể: tách quyền sửa, giữ snapshot ở một thời điểm, đáp ứng API mà caller có thể dùng độc lập, giữ lịch sử, hoặc bảo vệ invariant.

Nếu không có yêu cầu đó, copy có thể làm tăng allocation, bộ nhớ và độ phức tạp mà không nâng correctness.

### 1.1. Ba trục quyết định

| Trục | Câu hỏi cần trả lời | Ảnh hưởng tới cách copy |
| --- | --- | --- |
| **Ownership** | Ai chịu trách nhiệm bảo vệ/quản lý state? Ai có thể giữ alias? | Xác định nơi đặt defensive boundary |
| **Mutability** | State tham gia hợp đồng có thể thay đổi không? Elements/nested objects mutable không? | Chọn share, shallow hay selective deep copy |
| **Lifetime/observation** | Consumer cần trạng thái hiện tại hay một bản chụp bất biến tại thời điểm T? | Chọn live reference/view hay immutable snapshot |

Nếu một method chỉ cần **đọc tạm** một immutable `String`, không cần clone String. Nếu constructor lưu `int[]` input để đọc về sau và caller vẫn có thể mutate mảng, cần sao chép dữ liệu hoặc công bố rõ shared-mutable contract.

### 1.2. Quyền sở hữu (*ownership*) là hợp đồng thiết kế, không phải keyword Java

Java có `private`, `final`, GC, access controls và concurrent primitives, nhưng **không có compile-time affine/move-only ownership types** như một số ngôn ngữ khác. Một reference có thể bị alias:

~~~java
List<String> draft = new ArrayList<>();
List<String> alias = draft;
service.accept(draft);
~~~

Dù API tài liệu nói “service nhận ownership”, caller vẫn còn `alias` và có thể mutate list, trừ khi chương trình tuân quy ước hoặc service defensive-copy. Vì vậy khi nói *transfer ownership* trong Java thường là **quy ước phối hợp** hoặc được thực thi qua API wrapper/protocol, không phải JVM tự vô hiệu hóa aliases.

## 2. Bản đồ lựa chọn ngắn

| Hoàn cảnh | Chiến lược thường hợp lý | Cần lưu ý |
| --- | --- | --- |
| Component thật sự immutable, chia sẻ rộng | **Share reference** | Không dùng `==` làm value equality |
| Mutable data chỉ tồn tại trong một method, ownership độc quyền | **Mutate tại chỗ**, chưa cần copy | Không để reference thoát phạm vi ngoài ý muốn |
| Caller đưa mutable input, callee cần giữ snapshot | **Copy ở input boundary** | Copy cả mutable elements nếu cần |
| Callee giữ mutable internal state, caller cần đọc an toàn | **Immutable snapshot hoặc defensive output copy** | Không trả raw internal list/array |
| Hai collections cần cấu trúc độc lập nhưng elements được phép share | **Shallow container copy** | Mutate shared element ảnh hưởng cả hai |
| Consumer cần một value snapshot bất biến | **Selective deep copy sang immutable representation** | Copy đúng dữ liệu observable cần giữ |
| Consumer cần thấy thay đổi live state | **Share reference/live view có chủ đích** | Synchronization, ownership và lifetime rõ |
| Dữ liệu lớn, nhiều versions đọc chung | **Immutable structural sharing/persistent structures** nếu thích hợp | `List.copyOf` không mặc định là persistent data structure |
| Object giữ socket/connection/stream | **Không deep-clone resource tùy tiện** | Owner/borrower và close semantics |
| Graph có cycles và shared nodes | **Graph-aware copy** với identity memo khi cần | Giữ alias/cycle invariants |
| HashMap key mutable | **Snapshot immutable key** | Equality/hash-relevant state phải ổn định |

Đây là **cây định hướng**, không phải quy tắc “một kiểu Java luôn phải copy”. API domain và khả năng thay đổi thực tế của *toàn bộ object graph* mới quyết định.

## 3. Aliasing: vì sao chỉ nhìn object ngoài là chưa đủ?

Giả sử:

~~~java
class Order {
    String id;
    Address shippingAddress;
}
~~~

Một copy constructor có thể tạo Order mới nhưng gán `shippingAddress = source.shippingAddress`. Khi đó:

- Hai Order objects có identity khác nhau.
- Cùng một mutable Address object được tham chiếu.
- Gán lại `copy.id` không sửa `source.id`.
- Gán lại `copy.shippingAddress` không sửa field của source (nếu outer objects khác).
- Nhưng gọi `copy.shippingAddress.setCity(...)` có thể sửa Address mà cả source cũng quan sát.

Đây là **sao chép nông**: primitive values và reference values của fields được copy, nhưng nested objects không tự copy.

### 3.1. Chương trình: chọn copy phù hợp với child mutable

Lưu **`CopyDepthDecisionDemo.java`**:

~~~java
public class CopyDepthDecisionDemo {
    static final class Address {
        private String city;

        Address(String city) {
            this.city = city;
        }

        Address(Address source) {
            this.city = source.city;
        }

        void moveTo(String next) {
            city = next;
        }

        String city() {
            return city;
        }
    }

    static final class Person {
        private String name;
        private Address address;

        Person(String name, Address address) {
            this.name = name;
            this.address = address;
        }

        Person shallowCopy() {
            return new Person(name, address);
        }

        Person independentAddressCopy() {
            return new Person(name, new Address(address));
        }

        String description() {
            return name + "@" + address.city();
        }
    }

    public static void main(String[] args) {
        Person original = new Person(
                "Lan", new Address("Ha Noi"));
        Person shallow = original.shallowCopy();
        Person separate = original.independentAddressCopy();

        System.out.println("same outer=" +
                (original == shallow));
        System.out.println("shared address=" +
                (original.address == shallow.address));
        System.out.println("separate address=" +
                (original.address == separate.address));

        shallow.name = "Minh";
        shallow.address.moveTo("Hue");

        System.out.println("original=" + original.description());
        System.out.println("shallow=" + shallow.description());
        System.out.println("separate=" + separate.description());
    }
}
~~~

Biên dịch/chạy Java 17+:

~~~bash
javac CopyDepthDecisionDemo.java
java CopyDepthDecisionDemo
~~~

**Stdout:**

~~~text
same outer=false
shared address=true
separate address=false
original=Lan@Hue
shallow=Minh@Hue
separate=Lan@Ha Noi
~~~

**Phân tích:**

- `Person.shallowCopy` tạo outer object mới nhưng dùng chung Address.
- `Person.independentAddressCopy` tạo Address mới (đủ sâu vì Address ở đây chỉ giữ String immutable).
- Sửa name field trong shallow không làm original đổi name; sửa mutable Address chung thì original thấy Hue.
- Bản separate giữ Ha Noi vì không có alias tới Address đã bị sửa.
- Không nên gọi `independentAddressCopy` là “deep clone vĩnh viễn” nếu mai sau Address thêm nested mutable fields; contract phải được bảo trì khi cấu trúc class thay đổi.

## 4. Thuật ngữ ownership nên dùng nhất quán

### 4.1. Owned mutable value

Một object quản lý mutable component và không cho bên ngoài giữ references có khả năng sửa nó. Ví dụ: một `OrderAggregate` giữ mutable `ArrayList` nội bộ, chỉ cung cấp domain methods `addLine` có validation.

Ở đây **không cần copy khi tự xử lý nội bộ** trong cùng owner nếu không có rủi ro alias/temporal snapshot. Nhưng khi xuất dữ liệu ra caller, có thể cần snapshot.

### 4.2. Borrowed reference

Một method nhận reference để **dùng tạm** mà không sở hữu lâu dài. Nếu chỉ đọc đồng bộ và trả về trước khi caller mutate, có thể không cần copy.

Tuy nhiên, nếu method lưu reference vào field hoặc submit callback chạy về sau, nó **đã kéo dài lifetime** vượt phạm vi borrow; cần cập nhật contract hoặc copy để tránh caller mutation sau lời gọi.

### 4.3. Shared ownership / live reference

Nhiều components cùng quản lý hoặc sử dụng một object, muốn nhìn state sống thay đổi. Không copy là chủ đích. Phải nói rõ cách đồng bộ, lifecycle, permissions và người có quyền thay state.

### 4.4. Transfer-of-ownership convention

Caller trao reference cho một receiver và **cam kết không dùng/mutate nữa**. Java không tự enforce điều này. Nếu receiver không kiểm soát mọi aliases, có thể bị phá bất biến; hoặc dùng immutable representation, hoặc copy ở transfer boundary.

### 4.5. Immutable shared value

Nhiều owners/readers giữ reference tới cùng immutable `LocalDate`, `String`, `BigDecimal`, immutable record ... Không cần nhân bản chỉ để chống mutation của chính value ấy.

**Lưu ý:** một `record` giữ `int[]` hoặc mutable `List<Item>` **không tự được coi deep immutable**.

## 5. Borrowed, retained và snapshot là ba hợp đồng khác

Một method:

~~~java
void readNow(List<String> items) {
    System.out.println(items.size());
}
~~~

là mảnh minh họa của **borrowing ngắn hạn**: nó chỉ đọc size rồi trả. Nếu không có concurrent mutation ngoài ý muốn và không giữ alias, copy chưa chắc có lợi.

Một constructor:

~~~java
class SavedReport {
    private final List<String> lines;

    SavedReport(List<String> input) {
        lines = List.copyOf(input);
    }
}
~~~

thể hiện **retained snapshot**: lưu cấu trúc list tại thời điểm xây. Vì String immutable, đây là snapshot giá trị văn bản ổn định.

Trái lại:

~~~java
class LivePanel {
    private final List<String> shared;

    LivePanel(List<String> shared) {
        this.shared = shared;
    }
}
~~~

có thể là **live reference** nếu API công bố rằng panel phản ánh changes bên ngoài. Đây không mặc nhiên sai; vấn đề là **caller và callee phải đồng ý cùng một contract**, đặc biệt trong concurrent code.

## 6. Chương trình: giữ reference hay chụp snapshot?

Lưu **`BorrowOrSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class BorrowOrSnapshotDemo {
    static final class LiveViewer {
        private final List<String> source;

        LiveViewer(List<String> source) {
            this.source = source;
        }

        int size() {
            return source.size();
        }
    }

    static final class FrozenReport {
        private final List<String> lines;

        FrozenReport(List<String> source) {
            lines = List.copyOf(source);
        }

        int size() {
            return lines.size();
        }
    }

    public static void main(String[] args) {
        List<String> draft = new ArrayList<>(List.of("A"));
        LiveViewer live = new LiveViewer(draft);
        FrozenReport frozen = new FrozenReport(draft);

        System.out.println("before live=" + live.size());
        System.out.println("before frozen=" + frozen.size());

        draft.add("B");

        System.out.println("after live=" + live.size());
        System.out.println("after frozen=" + frozen.size());
    }
}
~~~

Chạy:

~~~bash
javac BorrowOrSnapshotDemo.java
java BorrowOrSnapshotDemo
~~~

Output:

~~~text
before live=1
before frozen=1
after live=2
after frozen=1
~~~

**LiveViewer** chủ đích quan sát list source khi source thay đổi. **FrozenReport** giữ snapshot cấu trúc với String immutable elements. Cả hai có thể đúng, nhưng tên lớp/hợp đồng phải nói rõ thứ người dùng cần.

`LiveViewer` trong ví dụ **không thread-safe** nếu list bị thay đổi đồng thời không có synchronization. Chương trình chỉ thay list tuần tự trong main.

## 7. Defensive copy ở ranh giới đầu vào

Khi constructor hoặc method cần lưu mutable input để sử dụng sau, hãy hỏi: **caller còn giữ reference không?** Nếu có, và callee cần state riêng, lưu raw reference là một lỗ hổng ownership.

Ví dụ sai:

~~~java
class UnsafeImage {
    private final byte[] pixels;

    UnsafeImage(byte[] pixels) {
        this.pixels = pixels;
    }
}
~~~

Dù field `private final`, caller giữ `pixels` vẫn có thể `pixels[0] = ...` làm dữ liệu trong UnsafeImage bị thay đổi.

Cách sửa tối thiểu cho primitive array là defensive clone:

~~~java
class Image {
    private final byte[] pixels;

    Image(byte[] input) {
        pixels = input.clone();
    }

    byte[] pixels() {
        return pixels.clone();
    }
}
~~~

Copy ở constructor tách **input alias**; copy ở getter tách **output alias**. Nếu chỉ làm một phía, phía còn lại vẫn có thể sửa internal array.

## 8. Chương trình: defensive copy hai chiều

Lưu **`DefensiveBoundaryDemo.java`**:

~~~java
import java.util.Arrays;

public class DefensiveBoundaryDemo {
    static final class KeyBytes {
        private final byte[] bytes;

        KeyBytes(byte[] source) {
            bytes = source.clone();
        }

        byte[] copyBytes() {
            return bytes.clone();
        }

        int checksumForDemo() {
            int total = 0;
            for (byte item : bytes) {
                total += item;
            }
            return total;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof KeyBytes key
                    && Arrays.equals(bytes, key.bytes);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(bytes);
        }
    }

    public static void main(String[] args) {
        byte[] original = {1, 2, 3};
        KeyBytes key = new KeyBytes(original);
        KeyBytes same = new KeyBytes(new byte[] {1, 2, 3});

        System.out.println("initial equality=" + key.equals(same));
        System.out.println("hash equality=" +
                (key.hashCode() == same.hashCode()));

        original[0] = 9;
        byte[] outgoing = key.copyBytes();
        outgoing[1] = 8;

        System.out.println("source changed=" + original[0]);
        System.out.println("outgoing changed=" + outgoing[1]);
        System.out.println("internal checksum=" +
                key.checksumForDemo());
        System.out.println("equality after=" + key.equals(same));
    }
}
~~~

Chạy:

~~~bash
javac DefensiveBoundaryDemo.java
java DefensiveBoundaryDemo
~~~

Output:

~~~text
initial equality=true
hash equality=true
source changed=9
outgoing changed=8
internal checksum=6
equality after=true
~~~

Kết quả chứng minh copies ở hai ranh giới tách external aliases khỏi internal mutable byte array. `checksumForDemo` chỉ cộng các bytes để minh họa state, **không** phải cryptographic checksum/hashing bảo mật.

## 9. Copy nông của collection thường là đủ khi element immutable

Với `List<String>` hoặc `List<LocalDate>`, hai lists khác nhau có thể giữ references tới cùng immutable elements mà không lo elements bị mutate.

~~~java
List<String> mutableCopy = new ArrayList<>(source);
List<String> readOnlySnapshot = List.copyOf(source);
~~~

Lựa chọn phụ thuộc yêu cầu:

- `new ArrayList<>(source)`: list structure mới, **mutable**; element references được copy.
- `List.copyOf(source)`: unmodifiable list giữ element values tại thời điểm snapshot; **không deep-copy** elements. Nó có thể tái sử dụng instance phù hợp khi source vốn unmodifiable, nên không cam kết outer identity luôn khác.
- `Collections.unmodifiableList(source)`: unmodifiable **view**; source có thể vẫn mutate sau đó và view nhìn thấy changes.
- `source` reference trực tiếp: chính cùng list object.

### 9.1. Bảng “new container” khác “new element”

| API/operation | Outer structure mới? | Component objects mới? | Caller sửa structure qua result? |
| --- | --- | --- | --- |
| `alias = source` | Không | Không | Theo source |
| `new ArrayList<>(source)` | Có | Không | Có |
| `source.toArray()` | Tạo array mới | Không | Có thể thay element references trong array |
| `intArray.clone()` | Có | Primitives values được copy | Có |
| `ItemArray.clone()` | Có | Không, Item references shared | Có |
| `List.copyOf(source)` | Không nhất thiết identity mới | Không | Không |
| `Collections.unmodifiableList(source)` | Wrapper/view; backing chung | Không | Không qua view |
| `Map.copyOf(source)` | Snapshot unmodifiable structure | Không clone keys/values | Không |

Một API copy có thể **không cấp phát object mới** khi cấu trúc/value bất biến đã hợp lệ. Đừng dựa vào `==` để yêu cầu identity mới nếu documentation chỉ cam kết snapshot/value semantics.

## 10. Chương trình: cùng element, khác list structure

Lưu **`CollectionChoiceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class CollectionChoiceDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        List<String> editable = new ArrayList<>(source);
        List<String> snapshot = List.copyOf(source);
        List<String> view = Collections.unmodifiableList(source);

        source.add("B");
        editable.add("C");

        System.out.println("source=" + source);
        System.out.println("editable=" + editable);
        System.out.println("snapshot=" + snapshot);
        System.out.println("view=" + view);

        try {
            snapshot.add("D");
        } catch (UnsupportedOperationException expected) {
            System.out.println("snapshot cannot add");
        }

        try {
            view.clear();
        } catch (UnsupportedOperationException expected) {
            System.out.println("view cannot clear");
        }
    }
}
~~~

Chạy:

~~~bash
javac CollectionChoiceDemo.java
java CollectionChoiceDemo
~~~

Output:

~~~text
source=[A, B]
editable=[A, C]
snapshot=[A]
view=[A, B]
snapshot cannot add
view cannot clear
~~~

Đây là lựa chọn phụ thuộc nhu cầu: bản copy mutable để chủ động sửa; snapshot để lưu giá trị cấu trúc; live view để theo dõi source mà không cho caller sửa qua wrapper.

## 11. Mutable elements: copy list chưa đủ bảo vệ values

Với `List<MutableItem>`, gọi `new ArrayList<>(source)` hoặc `List.copyOf(source)` vẫn giữ references tới Items hiện có. Nếu Item có setter và caller còn alias, state quan sát qua cả hai containers có thể đổi.

### 11.1. Chương trình phản ví dụ

Lưu **`MutableElementSharingDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class MutableElementSharingDemo {
    static final class Item {
        private String name;

        Item(String name) {
            this.name = name;
        }

        void rename(String next) {
            name = next;
        }

        String name() {
            return name;
        }
    }

    public static void main(String[] args) {
        Item item = new Item("old");
        List<Item> source = new ArrayList<>();
        source.add(item);

        List<Item> editable = new ArrayList<>(source);
        List<Item> snapshot = List.copyOf(source);

        System.out.println("same element=" +
                (source.get(0) == editable.get(0)));
        System.out.println("snapshot same element=" +
                (source.get(0) == snapshot.get(0)));

        item.rename("new");
        editable.add(new Item("extra"));

        System.out.println("source name=" + source.get(0).name());
        System.out.println("editable name=" + editable.get(0).name());
        System.out.println("snapshot name=" + snapshot.get(0).name());
        System.out.println("source size=" + source.size());
        System.out.println("editable size=" + editable.size());
        System.out.println("snapshot size=" + snapshot.size());
    }
}
~~~

Chạy:

~~~bash
javac MutableElementSharingDemo.java
java MutableElementSharingDemo
~~~

Output:

~~~text
same element=true
snapshot same element=true
source name=new
editable name=new
snapshot name=new
source size=1
editable size=2
snapshot size=1
~~~

Sao chép cấu trúc là một quyết định riêng; tách mutable elements là quyết định khác. Nếu yêu cầu “lưu tên hàng hóa lúc chốt đơn”, copy reference `Item` có thể sai vì tên/giá bị chỉnh sau này.

## 12. Selective copy: lưu giá trị nghiệp vụ thay vì clone cả graph

Một API báo giá cần **giá tại thời điểm đặt hàng**, không cần chia sẻ live Product.price của catalog. Thay vì clone cả Product entity (ID, cache, listeners, database hooks), hãy chuyển dữ liệu cần giữ thành immutable value record.

### 12.1. Ví dụ chọn đúng representation

Lưu **`SelectiveSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SelectiveSnapshotDemo {
    static final class MutableProduct {
        private final String sku;
        private long price;

        MutableProduct(String sku, long price) {
            this.sku = sku;
            this.price = price;
        }

        void setPrice(long price) {
            this.price = price;
        }

        String sku() {
            return sku;
        }

        long price() {
            return price;
        }
    }

    record QuotedLine(String sku, long unitPrice) {
    }

    static final class Quote {
        private final List<QuotedLine> lines;

        Quote(List<MutableProduct> products) {
            List<QuotedLine> snapshot = new ArrayList<>();
            for (MutableProduct p : products) {
                snapshot.add(new QuotedLine(p.sku(), p.price()));
            }
            lines = List.copyOf(snapshot);
        }

        long priceAt(int index) {
            return lines.get(index).unitPrice();
        }

        int size() {
            return lines.size();
        }
    }

    public static void main(String[] args) {
        MutableProduct product = new MutableProduct("PEN", 10);
        List<MutableProduct> catalog = new ArrayList<>();
        catalog.add(product);

        Quote saved = new Quote(catalog);

        product.setPrice(25);
        catalog.add(new MutableProduct("BOOK", 50));

        System.out.println("catalog price=" + product.price());
        System.out.println("saved price=" + saved.priceAt(0));
        System.out.println("catalog count=" + catalog.size());
        System.out.println("saved count=" + saved.size());
    }
}
~~~

Chạy:

~~~bash
javac SelectiveSnapshotDemo.java
java SelectiveSnapshotDemo
~~~

Output:

~~~text
catalog price=25
saved price=10
catalog count=2
saved count=1
~~~

**Tại sao tốt hơn “deep clone Product”?** Quote chỉ cần `sku` và `unitPrice` tại thời điểm chụp. Immutable record QuotedLine sở hữu dữ liệu ngắn gọn, không kéo theo khả năng mutate Product, connections hoặc cache.

**Concurrency caveat:** nếu catalog và prices có thể đổi đồng thời trong lúc constructor duyệt list, cần snapshot consistency/locking/transaction ở layer thích hợp. Việc chọn record không tự biến một lần đọc nhiều mutable objects thành atomic snapshot.

## 13. Immutable component nên share, không nhân bản vô ích

Java `String`, `LocalDate`, `BigInteger`, `BigDecimal` và records chỉ chứa immutable components là những value types có thể chia sẻ reference an toàn đối với mutation của **chính component**.

Ví dụ:

~~~java
record Coordinate(int x, int y) {
}

Coordinate shared = new Coordinate(1, 2);
Coordinate left = shared;
Coordinate right = shared;
~~~

Không có method hợp lệ để đổi `x` của shared. Không cần `new Coordinate(shared.x(), shared.y())` chỉ để chống ai đó mutate Coordinate.

**Nhưng** record với `int[] pixels`, `List<MutableItem>` hoặc reference tới resource không tự deep immutable. Nếu contract cần ổn định, kiểm tra state reachable qua các components.

### 13.1. Chương trình: chia sẻ immutable parts

Lưu **`ImmutablePartSharingDemo.java`**:

~~~java
public class ImmutablePartSharingDemo {
    record Point(int x, int y) {
        Point translated(int dx, int dy) {
            return new Point(x + dx, y + dy);
        }
    }

    record Segment(Point from, Point to) {
    }

    public static void main(String[] args) {
        Point shared = new Point(1, 2);
        Segment first = new Segment(shared, new Point(3, 4));
        Segment second = new Segment(shared, new Point(5, 6));

        System.out.println("shared endpoint=" +
                (first.from() == second.from()));

        Segment moved = new Segment(
                first.from().translated(10, 0),
                first.to());

        System.out.println("first from=" + first.from());
        System.out.println("moved from=" + moved.from());
        System.out.println("second from=" + second.from());
        System.out.println("same old endpoint=" +
                (first.from() == second.from()));
    }
}
~~~

Chạy:

~~~bash
javac ImmutablePartSharingDemo.java
java ImmutablePartSharingDemo
~~~

Output:

~~~text
shared endpoint=true
first from=Point[x=1, y=2]
moved from=Point[x=11, y=2]
second from=Point[x=1, y=2]
same old endpoint=true
~~~

Lời gọi `translated` trả Point mới. Không có mutation của Point chung; hai Segments cũ vẫn dùng reference shared. Đây là ví dụ cho **selective allocation**: chỉ tạo những values thực sự thay đổi.

## 14. Copy constructor hay `clone()`, factory, record?

### 14.1. Copy constructor

~~~java
class Config {
    private final String name;
    private final int[] weights;

    Config(Config source) {
        name = source.name;             // Share immutable String.
        weights = source.weights.clone(); // Copy mutable array.
    }
}
~~~

Đây là mảnh minh họa class có fields tương ứng và constructor/factory cần thiết. Copy constructor giúp định nghĩa **từng field**: share phần immutable, copy phần mutable.

### 14.2. Static factory

~~~java
static Config snapshotOf(Config source) {
    return new Config(source);
}
~~~

Tên `snapshotOf` diễn đạt **mục đích nghiệp vụ** rõ hơn `clone`, có thể bổ sung validation/normalization, nhưng implementation vẫn phải giữ đúng semantics cam kết.

### 14.3. `Object.clone()`

`Object.clone` mặc định sao chép field values: primitive values được copy, reference values **vẫn trỏ tới cùng child objects**, tức shallow copy. `Cloneable` là marker interface không khai báo `clone()` public. Cơ chế cloning có hạn chế với final fields, invariants, resource ownership và subclasses.

Không chọn `clone` chỉ vì tên nghe giống “sao chép sâu”; muốn tách mutable components phải viết logic riêng. Với class có final state và complex invariants, copy constructor/factory thường dễ kiểm soát hơn.

### 14.4. Record

Record có final component fields và generated accessors/methods, nhưng truyền raw array vào component không tự clone mảng. Nếu model là immutable values, record components phải cũng immutable hoặc được bảo vệ bằng defensive copy tương ứng.

### 14.5. Chọn theo contract, không theo API name

Không có yêu cầu universal “phải dùng clone” hoặc “copy constructor là deep”. Tên method nên phản ánh **mức độc lập** mà người dùng cần.

## 15. Chương trình: copy constructor chia sẻ phần an toàn

Lưu **`SelectiveCopyConstructorDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class SelectiveCopyConstructorDemo {
    static final class Plan {
        private final String id;
        private final int[] hours;

        Plan(String id, int[] hours) {
            this.id = Objects.requireNonNull(id, "id");
            this.hours = hours.clone();
        }

        Plan(Plan source) {
            this.id = source.id;
            this.hours = source.hours.clone();
        }

        int totalHours() {
            return Arrays.stream(hours).sum();
        }

        int[] copyHours() {
            return hours.clone();
        }

        String id() {
            return id;
        }
    }

    public static void main(String[] args) {
        int[] draft = {2, 3};
        Plan original = new Plan("A", draft);
        Plan copy = new Plan(original);

        System.out.println("same plan=" + (original == copy));
        System.out.println("same id reference=" +
                (original.id() == copy.id()));

        draft[0] = 99;
        int[] outgoing = copy.copyHours();
        outgoing[1] = 88;

        System.out.println("original total=" +
                original.totalHours());
        System.out.println("copy total=" + copy.totalHours());
    }
}
~~~

Chạy:

~~~bash
javac SelectiveCopyConstructorDemo.java
java SelectiveCopyConstructorDemo
~~~

Output:

~~~text
same plan=false
same id reference=true
original total=5
copy total=5
~~~

Hai Plans có identity khác nhau, chia sẻ immutable String ID, nhưng copy riêng mutable `int[]`. Constructor ban đầu cũng clone draft; accessor chỉ trả clone. Đây là ví dụ **copy vừa đủ**: không copy String để “deep” hơn.

### 15.1. Vì sao identity của String trên đây chắc chắn true?

Copy constructor gán trực tiếp `this.id = source.id`; hai fields giữ **cùng reference value**. Kết quả không dựa vào JVM String intern/caching. Không dùng identity comparison để so String contents trong nghiệp vụ — ở đây chỉ kiểm tra quyền chia sẻ component.

## 16. Ownership không thể “chuyển” bằng lời nói suông

Một API có thể ghi:

~~~java
void takeOwnership(List<String> list) {
    this.items = list;
}
~~~

Nếu caller còn giữ `list` hoặc một alias khác, nó vẫn có thể `add/remove` làm thay state receiver. Java không vô hiệu các references cũ khi passed by value.

### 16.1. Chương trình chứng minh rủi ro transfer convention

Lưu **`OwnershipTransferConventionDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class OwnershipTransferConventionDemo {
    static final class Warehouse {
        private final List<String> items;

        Warehouse(List<String> transferred) {
            // Chỉ an toàn nếu caller thực sự ngừng dùng mọi alias.
            items = transferred;
        }

        String contents() {
            return items.toString();
        }
    }

    static final class SafeWarehouse {
        private final List<String> items;

        SafeWarehouse(List<String> source) {
            items = List.copyOf(source);
        }

        String contents() {
            return items.toString();
        }
    }

    public static void main(String[] args) {
        List<String> draft = new ArrayList<>(List.of("A"));
        List<String> alias = draft;

        Warehouse live = new Warehouse(draft);
        SafeWarehouse saved = new SafeWarehouse(draft);

        alias.add("B");

        System.out.println("live=" + live.contents());
        System.out.println("saved=" + saved.contents());
    }
}
~~~

Chạy:

~~~bash
javac OwnershipTransferConventionDemo.java
java OwnershipTransferConventionDemo
~~~

Output:

~~~text
live=[A, B]
saved=[A]
~~~

**Giải thích:** caller tuy “đưa” draft vào Warehouse nhưng vẫn có alias và sửa nó. Warehouse đọc giá trị live. SafeWarehouse copy structure ngay tại boundary, nên có snapshot không bị alias structure thay đổi. Vì elements là immutable String, snapshot này đủ.

Nếu muốn thật sự share live structure, Warehouse có thể là đúng **khi API công khai semantics ấy**; nó chỉ sai nếu receiver hứa một snapshot riêng.

## 17. Object graph có cycles: copy từng node phải giữ identity logic

Khi object graph có vòng A→B→A hoặc hai edges trỏ cùng child, copy nông một node giữ nguyên references tới graph cũ. Nếu business yêu cầu copy **toàn bộ owned subgraph**, phải dựng lại references cho graph mới.

Một deep-copy ngây thơ gọi đệ quy không nhớ nodes đã thăm sẽ có nguy cơ `StackOverflowError` với cycles hoặc tạo nhiều copies cho một shared node.

Cách phổ biến là memoization theo **reference identity**: `IdentityHashMap<OldNode, NewNode>`. Ghi mapping ngay khi tạo bản sao outer node, rồi copy các edges theo đệ quy; lần gặp lại node cũ dùng bản copy đã tồn tại.

### 17.1. Chương trình graph copy có bảo toàn alias và cycle

Lưu **`GraphOwnershipCopyDemo.java`**:

~~~java
import java.util.IdentityHashMap;

public class GraphOwnershipCopyDemo {
    static final class Node {
        String label;
        Node next;
        Node shortcut;

        Node(String label) {
            this.label = label;
        }
    }

    static Node copyGraph(
            Node root, IdentityHashMap<Node, Node> seen) {
        if (root == null) {
            return null;
        }

        Node existing = seen.get(root);
        if (existing != null) {
            return existing;
        }

        Node result = new Node(root.label);
        seen.put(root, result);

        result.next = copyGraph(root.next, seen);
        result.shortcut = copyGraph(root.shortcut, seen);
        return result;
    }

    static Node copyGraph(Node root) {
        return copyGraph(root, new IdentityHashMap<>());
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");

        a.next = b;
        a.shortcut = b;
        b.next = a;

        Node copied = copyGraph(a);

        System.out.println("new root=" + (copied != a));
        System.out.println("new child=" + (copied.next != b));
        System.out.println("shared edges=" +
                (copied.next == copied.shortcut));
        System.out.println("cycle preserved=" +
                (copied.next.next == copied));

        copied.next.label = "NEW";
        System.out.println("original child=" + b.label);
        System.out.println("copied child=" + copied.next.label);
    }
}
~~~

Chạy:

~~~bash
javac GraphOwnershipCopyDemo.java
java GraphOwnershipCopyDemo
~~~

Output:

~~~text
new root=true
new child=true
shared edges=true
cycle preserved=true
original child=B
copied child=NEW
~~~

**Quan trọng về phạm vi copy:** code này copy **toàn bộ Node graph reachable** theo các edges `next` và `shortcut`. Nó chỉ thích hợp nếu caller có quyền tạo phiên bản graph mới với semantics đó. Nếu một edge trỏ tới shared service/resource bên ngoài, không nên tùy tiện deep-copy resource; thay chính sách theo từng loại edge.

Ở graph lớn, còn cần quan tâm recursion depth, memory use, concurrent mutations và snapshot consistency.

## 18. Shared mutable resources không phải value objects để clone

File handles, sockets, database connections, executors, native buffers và transaction contexts có ownership/lifecycle riêng. Một copy constructor của wrapper có thể tạo wrapper mới nhưng **vẫn giữ cùng resource reference**.

Nếu wrapper A close resource, wrapper B cũng có thể mất khả năng sử dụng. Đó là **shared resource ownership**, không phải deep copy.

### 18.1. Chương trình resource được mượn và đóng

Lưu **`ResourceOwnershipDemo.java`**:

~~~java
public class ResourceOwnershipDemo {
    static final class Resource implements AutoCloseable {
        private boolean closed;

        String status() {
            return closed ? "closed" : "open";
        }

        @Override
        public void close() {
            closed = true;
        }
    }

    static final class BorrowingClient {
        private final Resource resource;

        BorrowingClient(Resource resource) {
            this.resource = resource;
        }

        BorrowingClient(BorrowingClient source) {
            resource = source.resource;
        }

        String observe() {
            return resource.status();
        }

        // Không close ở đây vì client chỉ mượn resource.
    }

    public static void main(String[] args) {
        Resource owner = new Resource();
        BorrowingClient one = new BorrowingClient(owner);
        BorrowingClient two = new BorrowingClient(one);

        System.out.println("before one=" + one.observe());
        System.out.println("before two=" + two.observe());

        owner.close();

        System.out.println("after one=" + one.observe());
        System.out.println("after two=" + two.observe());
    }
}
~~~

Chạy:

~~~bash
javac ResourceOwnershipDemo.java
java ResourceOwnershipDemo
~~~

Output:

~~~text
before one=open
before two=open
after one=closed
after two=closed
~~~

Đây là resource mô phỏng để làm rõ **cùng reference + chung lifecycle**. Trong ứng dụng thực, close semantics có thể khác, và wrapper không được tiếp tục dùng resource đã đóng.

**Nguyên tắc:** xác định **một owner chịu trách nhiệm close** hoặc dùng cơ chế reference counting/lifecycle orchestration theo nhu cầu; không nhân bản/đóng tùy tiện chỉ vì outer wrapper đã “copy”.

## 19. Multithreading: copy nông không làm mutable child an toàn

Giả sử hai classes `SnapshotView` khác nhau cùng giữ reference tới một `MutableCounter`. Dù outer objects độc lập, hai threads dùng chúng vẫn có thể đọc/ghi **cùng counter**.

Với nhiều readers cần cùng dữ liệu **không đổi**, có thể snapshot **giá trị** sang immutable record. Nếu consumers cố ý dùng live counter, cần concurrency primitive/locks thích hợp.

### 19.1. Demo shared counter và immutable snapshot

Lưu **`SharedMutableCounterDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class SharedMutableCounterDemo {
    static final class Viewer {
        private final AtomicInteger counter;

        Viewer(AtomicInteger counter) {
            this.counter = counter;
        }

        Viewer(Viewer source) {
            this.counter = source.counter;
        }

        int current() {
            return counter.get();
        }
    }

    record CounterSnapshot(int value) {
    }

    public static void main(String[] args) {
        AtomicInteger shared = new AtomicInteger(5);
        Viewer first = new Viewer(shared);
        Viewer second = new Viewer(first);
        CounterSnapshot frozen = new CounterSnapshot(shared.get());

        System.out.println("same counter=" +
                (first.counter == second.counter));
        System.out.println("snapshot before=" + frozen.value());

        shared.incrementAndGet();

        System.out.println("first=" + first.current());
        System.out.println("second=" + second.current());
        System.out.println("snapshot after=" + frozen.value());
    }
}
~~~

Chạy:

~~~bash
javac SharedMutableCounterDemo.java
java SharedMutableCounterDemo
~~~

Output:

~~~text
same counter=true
snapshot before=5
first=6
second=6
snapshot after=5
~~~

`AtomicInteger` cung cấp atomic operations cho **một counter**; nó không biến một business transaction nhiều fields thành atomic operation. `CounterSnapshot` chụp primitive value, không còn live alias.

### 19.2. Publication và temporal snapshots

Immutable object graph nên được xây dựng hoàn chỉnh, rồi công bố reference theo Java Memory Model khi threads khác cần thấy phiên bản đó. `volatile`, locks, thread-safe queues/executors và appropriately constructed final fields có rules riêng.

Chỉ copy object **không tự giải quyết** data race khi source bị mutate đồng thời lúc snapshot đang được tạo; một value snapshot nhiều fields có thể chứa hỗn hợp những thời điểm khác nhau nếu không có synchronization/transaction thích hợp.

## 20. Chương trình: chia sẻ phiên bản immutable, thay reference tại owner

Lưu **`ImmutableVersionDemo.java`**:

~~~java
import java.util.List;

public class ImmutableVersionDemo {
    record Config(int version, List<String> features) {
        Config {
            features = List.copyOf(features);
        }
    }

    static final class ConfigHolder {
        private volatile Config current;

        ConfigHolder(Config initial) {
            current = initial;
        }

        Config snapshot() {
            return current;
        }

        void publish(Config next) {
            current = next;
        }
    }

    public static void main(String[] args) {
        ConfigHolder holder = new ConfigHolder(
                new Config(1, List.of("search")));

        Config old = holder.snapshot();

        holder.publish(new Config(
                2, List.of("search", "report")));

        Config recent = holder.snapshot();

        System.out.println("old version=" + old.version());
        System.out.println("old features=" + old.features());
        System.out.println("recent version=" + recent.version());
        System.out.println("recent features=" + recent.features());
    }
}
~~~

Chạy:

~~~bash
javac ImmutableVersionDemo.java
java ImmutableVersionDemo
~~~

Output:

~~~text
old version=1
old features=[search]
recent version=2
recent features=[search, report]
~~~

Đây là hai **immutable snapshots** với String elements, không có mutation của old. Holder dùng `volatile` reference để publish versions theo một cơ chế memory-visibility thông thường.

**Giới hạn:** `volatile` đơn lẻ không ngăn hai writers bị lost update trong read-modify-write workflow. Nếu cần compare-and-set, hãy xem `AtomicReference` hoặc synchronization phù hợp. Immutability tách tính ổn định của **mỗi phiên bản** khỏi coordination của **việc đổi phiên bản**.

## 21. Mutable hash keys: tại sao phải chọn snapshot theo identity ổn định

`HashMap`/`HashSet` giả định các thông tin dùng bởi `equals`/`hashCode` của key/element không bị thay đổi theo cách phá lookup trong thời gian key/element còn ở collection.

Một class mutable `Order` có fields `id`, `status`, `amount`. Nếu business identity là ID, bạn có thể chọn một immutable `OrderKey(id)` làm map key, thay vì dùng cả Order mutable. Điều này tách ownership của entity state khỏi key equality.

### 21.1. Chương trình snapshot key

Lưu **`StableKeySnapshotDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class StableKeySnapshotDemo {
    static final class MutableProduct {
        String sku;
        long price;

        MutableProduct(String sku, long price) {
            this.sku = sku;
            this.price = price;
        }

        void changePrice(long next) {
            price = next;
        }
    }

    record ProductKey(String sku) {
    }

    public static void main(String[] args) {
        MutableProduct product = new MutableProduct("PEN", 10);

        ProductKey stable = new ProductKey(product.sku);
        Map<ProductKey, String> map = new HashMap<>();
        map.put(stable, "item");

        product.changePrice(20);

        System.out.println("current price=" + product.price);
        System.out.println("key sku=" + stable.sku());
        System.out.println("lookup=" +
                map.get(new ProductKey("PEN")));
    }
}
~~~

Chạy:

~~~bash
javac StableKeySnapshotDemo.java
java StableKeySnapshotDemo
~~~

Output:

~~~text
current price=20
key sku=PEN
lookup=item
~~~

Key là immutable record chỉ chứa String SKU, và equality/hash theo SKU, nên thay mutable Product.price không làm key đổi. Điều này thích hợp **nếu SKU là business identity ổn định theo domain**. Nếu SKU có thể đổi hoặc tái sử dụng, cần định nghĩa key identity khác.

### 21.2. Copy list không giải quyết mutable key

`Map.copyOf` hoặc `new HashMap<>(sourceMap)` không tự deep-copy key objects. Nếu original map dùng mutable keys không ổn định, copy map structure vẫn dùng cùng keys theo reference. **Sửa key contract/ownership** chứ không chỉ tạo một map mới.

## 22. Copy-on-write và structural sharing

Khi dữ liệu có nhiều readers và ít writers, một cách thiết kế là **copy-on-write**:

1. Writer lấy version cũ.
2. Xây bản mới (copy cấu trúc cần thiết, chia sẻ immutable elements).
3. Publish reference tới version mới theo concurrency protocol.
4. Readers đã lấy version cũ tiếp tục đọc snapshot cũ.

### 22.1. Không phải `CopyOnWriteArrayList` cho mọi trường hợp

Java có `CopyOnWriteArrayList`, dùng copy-on-write với array cấu trúc nội bộ cho updates; thích hợp một số read-mostly workloads, nhưng writes có cost. Element objects vẫn có thể mutable.

### 22.2. Persistent data structures

Một persistent tree/list có thể chia sẻ **các nodes bất biến** giữa versions, thay vì copy toàn bộ. Nhưng bạn phải chọn cấu trúc/thư viện với hợp đồng phù hợp; `new ArrayList<>(source)` không tạo persistent list, và `List.copyOf` không bảo đảm thuật toán structural sharing nào cho arbitrary updates.

### 22.3. Khi copy ít hơn lại an toàn hơn

Nếu immutable tree node chứa immutable children, một bản cập nhật có thể chỉ tạo nodes trên đường từ root tới leaf được đổi, chia sẻ những nhánh còn lại. An toàn vì **không ai mutate shared nodes**.

Nếu shared nodes mutable, structural sharing phải đi kèm ownership/coordination cực rõ, nếu không những readers của old snapshot sẽ thấy changes không dự kiến.

## 23. Bản sao nông còn giữ graph backlinks như cũ

Một root A có child C, child C có backlink về A. Nếu shallow-copy A thành A2 bằng cách sao chép field `child`, A2 vẫn trỏ tới **C cũ**, và C vẫn trỏ về A cũ.

~~~text
A  ----child----> C ----parent----> A

A2 ----child----> C ----parent----> A
~~~

Nếu nghiệp vụ đòi `child.parent == newRoot`, shallow copy **không thỏa**, dù `newRoot != oldRoot`.

### 23.1. Hướng giải quyết

- Nếu chia sẻ C cố ý, đừng kỳ vọng backlink trỏ A2.
- Nếu cần copied owned graph, copy C và cập nhật C2.parent về A2.
- Nếu graph có cycles/multiple parents, dùng memoization identity map như ví dụ GraphOwnershipCopyDemo.
- Nếu edges trỏ external objects (shared service), cần xác định những cạnh nào **không** thuộc owned subgraph và giữ nguyên reference.
- Đảm bảo invariant của graph không bị broken ở giữa các bước trong môi trường concurrent.

## 24. Copy nhiều tầng: phải định nghĩa thế nào là “đủ sâu”

**Primitive array:** `int[]` clone tạo giá trị độc lập.

**Object array:** `Item[]` clone tạo array mới nhưng Item references shared.

**Matrix primitive:** `int[][]` clone chỉ outer, cần clone từng row nếu muốn tách rows. Null rows cần xử lý.

**List<List<String>>:** copy outer list không copy inner lists; nếu inner lists mutable, có thể cần snapshot từng inner list.

**List<ImmutableRecord>:** copy/snapshot outer list có thể đủ vì elements immutable, không cần tạo new record instances.

**Graph có cycle:** yêu cầu graph-aware copy nếu muốn độc lập ở toàn bộ owned nodes.

Một API viết “deep copy” cần nêu **ranh giới sở hữu/độ sâu**; không thể hiểu thành copy mọi thứ tới vô hạn, nhất là resources và external shared nodes.

### 24.1. Demo nested list snapshots

Lưu **`NestedListSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class NestedListSnapshotDemo {
    static List<List<String>> snapshot(
            List<List<String>> input) {
        List<List<String>> rows = new ArrayList<>();
        for (List<String> row : input) {
            rows.add(List.copyOf(row));
        }
        return List.copyOf(rows);
    }

    public static void main(String[] args) {
        List<String> row = new ArrayList<>(List.of("A"));
        List<List<String>> matrix = new ArrayList<>();
        matrix.add(row);

        List<List<String>> shallow = new ArrayList<>(matrix);
        List<List<String>> fixed = snapshot(matrix);

        row.add("B");
        matrix.add(new ArrayList<>(List.of("C")));

        System.out.println("source row=" + matrix.get(0));
        System.out.println("shallow row=" + shallow.get(0));
        System.out.println("fixed row=" + fixed.get(0));
        System.out.println("source rows=" + matrix.size());
        System.out.println("shallow rows=" + shallow.size());
        System.out.println("fixed rows=" + fixed.size());
    }
}
~~~

Chạy:

~~~bash
javac NestedListSnapshotDemo.java
java NestedListSnapshotDemo
~~~

Output:

~~~text
source row=[A, B]
shallow row=[A, B]
fixed row=[A]
source rows=2
shallow rows=1
fixed rows=1
~~~

Đây là **selective deep structural snapshot** của hai tầng lists, an toàn ở ví dụ vì String elements immutable. Nếu elements là mutable custom objects, còn cần snapshot chúng.

`List.copyOf` từ một source đang bị mutate **đồng thời** không tự tạo atomic multi-element snapshot; caller phải đảm bảo đầu vào ổn định hoặc dùng synchronization thích hợp.

## 25. Hiệu năng: “copy cho an toàn” cũng cần đo đúng

Một chương trình copy sâu vô điều kiện có thể:

- Tạo nhiều objects, tốn heap và GC.
- Tăng thời gian đi qua toàn bộ graph.
- Mất tính chia sẻ identity mà domain cần.
- Làm tốn I/O nếu cố serialize/deserialize mọi thứ.
- Gặp lỗi với cycles, non-serializable fields hoặc resource handles.
- Thêm complexity cho constructors/cloners.

Ngược lại, không copy khi cần independent snapshot có thể tạo bugs khó phát hiện.

### 25.1. Chi phí tham khảo, không phải benchmark

| Thao tác | Chi phí thường gặp theo kích thước n | Điều cần kiểm tra |
| --- | --- | --- |
| Gán reference | O(1) | Không có tách ownership |
| Copy `int[]` length n | O(n) | Values tách độc lập |
| Copy `ArrayList` length n | O(n) | Element references vẫn share |
| Snapshot nested list tổng m elements | O(m) tùy số tầng | Mutable elements chưa chắc copy |
| Copy graph V nodes, E edges | O(V+E) cho traversal tiêu chuẩn | Identity map, memory, cycles |
| Structural sharing update trong tree cân bằng | Có thể O(log n) tùy implementation | Không suy từ Java List.copyOf |
| Serialize→deserialize | Phụ thuộc format/graph/I/O | Không tự phù hợp resource/identity |

Những độ phức tạp này là mô hình thuật toán thông thường; implementation và workload thực tế cần profiling. Tối ưu có giá trị khi **correctness, ownership và contracts đã rõ**.

## 26. Khi nào nên dùng immutable snapshot từ đầu?

Nếu dữ liệu cần chia sẻ rộng (nhiều modules, caches, async handlers), thường đáng xây **immutable value representation** ở ranh giới.

Ưu điểm:

- Không cần copy lại một value thật sự immutable mỗi lần chuyển layer.
- Nhiều consumers có thể giữ reference mà không lo source mutate value.
- `equals`/`hashCode` ổn định nếu implementation đúng và fields thuộc immutable graph.
- Dễ tạo version mới, event và historical snapshot.
- Giảm nhu cầu locks riêng chỉ để bảo vệ state không đổi.

Cần nhớ **record không tự deep immutable**. Record giữ `byte[]`, `List<MutablePayload>` hay resource reference vẫn có thể quan sát mutation. Dùng immutable elements hoặc defensive copies theo đúng ownership boundary.

## 27. Chọn cách copy khi object còn thay đổi theo nghiệp vụ

Một domain entity như `BankAccount` hoặc `Order` có lifecycle mutable. Không nhất thiết biến toàn bộ entity thành immutable object và copy lại mỗi lần thay đổi; có thể dùng:

- Mutable aggregate bên trong boundary do service/transaction sở hữu.
- Immutable command DTO để nhận yêu cầu.
- Immutable snapshot/result DTO để trả dữ liệu ra ngoài.
- Immutable value object làm IDs, Money, Coordinates.
- Copy field-specific representation khi xuất báo cáo hoặc phát event.

**Không dùng bản copy shallow của mutable entity để thay cho snapshot giao dịch**: nó có thể giữ aliases tới nested mutable state, khiến report cũ nhìn thấy giá trị mới sau khi nghiệp vụ thay đổi.

### 27.1. Quy tắc “mutate locally, publish immutably”

Một chiến lược thực dụng:

1. Cho phép mutable builder/list tạm trong phạm vi sở hữu hẹp.
2. Validate/normalize dữ liệu trong lúc xây.
3. Chuyển sang immutable record/final value class, defensive-copy các mutable components.
4. Publish immutable result.
5. Mỗi lần update tạo version mới hoặc được owner kiểm soát rồi phát snapshot mới.

Nguyên tắc này hữu ích khi consumer không cần sửa nguồn, nhưng không thay quyền sở hữu resource hoặc transaction rules.

## 28. Chương trình tích hợp: builder mutable, immutable result, không copy String thừa

Lưu **`BuilderToSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class BuilderToSnapshotDemo {
    record Task(String title, int points) {
        Task {
            Objects.requireNonNull(title, "title");
            if (points < 0) {
                throw new IllegalArgumentException("points");
            }
        }
    }

    record Plan(List<Task> tasks) {
        Plan {
            tasks = List.copyOf(tasks);
        }

        int points() {
            int result = 0;
            for (Task task : tasks) {
                result = Math.addExact(result, task.points());
            }
            return result;
        }
    }

    static final class Builder {
        private final List<Task> tasks = new ArrayList<>();

        Builder add(Task task) {
            tasks.add(Objects.requireNonNull(task));
            return this;
        }

        Plan build() {
            return new Plan(tasks);
        }
    }

    public static void main(String[] args) {
        Builder builder = new Builder().add(new Task("A", 2));

        Plan first = builder.build();
        builder.add(new Task("B", 3));
        Plan second = builder.build();

        System.out.println("first size=" + first.tasks().size());
        System.out.println("first points=" + first.points());
        System.out.println("second size=" + second.tasks().size());
        System.out.println("second points=" + second.points());
        System.out.println("first task shared=" +
                (first.tasks().get(0) == second.tasks().get(0)));
    }
}
~~~

Chạy:

~~~bash
javac BuilderToSnapshotDemo.java
java BuilderToSnapshotDemo
~~~

Output:

~~~text
first size=1
first points=2
second size=2
second points=5
first task shared=true
~~~

Builder có mutable list nội bộ, nhưng Plan snapshots unmodifiable. `Task` records chỉ chứa immutable String/primitive nên chia sẻ Task reference giữa versions an toàn; **không cần clone Task**, kể cả khi outer list khác.

## 29. API contract: đặt tên và ghi chú không gây hiểu nhầm

Thay vì chỉ khai báo:

~~~java
Data copy();
~~~

hãy cân nhắc tên/hợp đồng:

- `shallowCopy()`: tạo outer object mới, reference components giữ nguyên.
- `toImmutableSnapshot()`: tạo giá trị ổn định theo tập fields được liệt kê.
- `copyWithOwnItems()`: tách owned mutable elements.
- `view()`: trả live view, có thể phản ánh source changes.
- `copyItems()`: trả mutable container mới với elements theo contract.
- `borrowResource()`: mượn handle, caller không sở hữu close.
- `withField(next)`: trả value object mới thay vì mutate original.

Những tên trên là **gợi ý design**, không phải methods có sẵn của Java. Tài liệu API vẫn phải trả lời: **outer identity mới? components nào shared? mutable? null? lifetime? ownership? thread safety?**.

### 29.1. Ví dụ hợp đồng minh bạch

Một constructor ghi:

> Giữ một **immutable snapshot** của danh sách dòng và các giá trị tiền tại thời điểm tạo. Caller có thể tiếp tục sửa collection gốc mà không ảnh hưởng invoice. Những String và immutable ID values có thể chia sẻ references.

rõ hơn câu:

> Constructor sao chép danh sách.

Bởi câu thứ hai không cho biết snapshot hay live, copy list hay copy từng element, mutable hay unmodifiable.

## 30. Sai lầm phổ biến và cách sửa

| Sai lầm | Cách hiểu/sửa |
| --- | --- |
| “`b = a` là shallow copy.” | Đây chỉ là reference assignment, không tạo outer mới |
| “Owner nhận reference là aliases bên ngoài tự mất hiệu lực.” | Java không có automatic move invalidation |
| “Final reference khiến object con immutable.” | Final ngăn gán field, không freeze referenced object |
| “Không có setter nên giữ raw mutable input an toàn.” | Caller còn alias, cần defensive copy nếu snapshot |
| “Getter trả internal array vì field private.” | Getter lộ alias; trả clone/snapshot theo contract |
| “Copy List nghĩa là clone mọi Item.” | List copy chỉ sao chép structure/references |
| “List.copyOf làm elements immutable.” | Unmodifiable structure, mutable elements vẫn shared |
| “Unmodifiable view là snapshot.” | View có thể phản ánh backing mutation |
| “Record luôn deep immutable.” | Record components có thể giữ mutable refs |
| “`clone()` luôn tạo deep copy.” | Object.clone mặc định field-by-field shallow copy |
| “Deep copy phải clone cả String và LocalDate.” | Immutable values có thể share reference |
| “Sao chép parent tự cập nhật child.parent.” | Backlink vẫn trỏ graph cũ nếu chỉ shallow copy |
| “Sao chép graph cứ đệ quy không cần map.” | Cycles/shared nodes cần identity memoization |
| “Copy wrapper có Connection là có Connection mới.” | Resource reference/lifecycle có thể shared |
| “Copy một object là đủ để có atomic snapshot từ nhiều threads.” | Source mutation đồng thời vẫn cần synchronization |
| “Immutable snapshot làm holder updates atomic.” | Việc publish/read-modify-write cần coordination |
| “Copy Map sửa được mutable key hash.” | Key references có thể còn mutable; snapshot key identity |
| “Không bao giờ copy là tối ưu.” | Snapshot correctness có thể đòi copy |
| “Luôn deep-copy tất cả là an toàn.” | Tốn chi phí, phá identity và không copy được resources |
| “Copy phải trả instance khác mọi lúc.” | Với immutable values/snapshot APIs có thể share/reuse |
| “Hash code giống nhau chứng minh same object.” | Hash collision hợp lệ, dùng `==` để so identity |
| “Copy làm GC thu hồi source ngay.” | GC dựa trên reachability; copies/aliases có thể kéo dài lifetime |

## 31. Checklist trước khi chọn một chiến lược

1. **Object nào thật sự thuộc sở hữu của module này?** Những references nào bên ngoài còn giữ?
2. **Dữ liệu có mutable không?** Cần xem nested arrays, collection elements, custom objects.
3. **Callee sẽ chỉ đọc tạm hay lưu reference qua lời gọi?**
4. **Người nhận cần live changes hay state chụp tại thời điểm T?**
5. **Có yêu cầu identity khác?** Result phải khác object hay chỉ cần value semantics?
6. **Có immutable components có thể chia sẻ để giảm copy không?**
7. **Một mutable component được phép share có ownership/concurrency rules không?**
8. **API cần copy ở input, output hay cả hai boundaries?**
9. **Nếu là list/map snapshot, elements/values cũng có thể bị sửa qua alias không?**
10. **Nếu copy graph, nodes/cycles/shared edges/backlinks phải giữ invariants nào?**
11. **Có external resource không được copy như value object không?**
12. **Có HashMap key tham gia equality/hash được sửa sau khi lưu không?**
13. **Source có bị threads khác thay trong lúc copy không?** Nếu có, consistency protocol nào?
14. **Một lần update phiên bản có cần atomic publication hoặc compare-and-set không?**
15. **Copy có thể tạo bao nhiêu objects?** Có đáng profiling không?
16. **Contract đã viết rõ lifetime, mutability và ownership transfer convention chưa?**
17. **Tests đã thử mutation qua input/output aliases và nested elements chưa?**
18. **Nếu lỗi do representation thay đổi về sau, test nào phát hiện việc copy không còn đủ sâu?**

## 32. Bài tập thực hành có đáp án

**Câu 1.** `Person b = a;` có tạo Person mới không?  
**Đáp án:** Không, chỉ sao chép giá trị reference sang biến b.

**Câu 2.** `new Person(a)` có chắc tạo deep copy không?  
**Đáp án:** Không. Copy constructor có thể shallow/deep/selective tùy body.

**Câu 3.** Khi nào chia sẻ `String`/`LocalDate` reference là hợp lý?  
**Đáp án:** Khi value ấy thực sự immutable và contract chỉ cần đọc, không cần object identity độc lập.

**Câu 4.** Mutable `Address` được Person shallow-copy, ai chịu mutation?  
**Đáp án:** Mọi aliases đến cùng Address có thể quan sát thay đổi; cần ownership/mutation contract.

**Câu 5.** Nếu copy Person khác outer identity, gán lại `copy.address` có tự sửa `original.address` không?  
**Đáp án:** Không, đó là field của outer copy, nếu không có side effects khác.

**Câu 6.** Nếu `copy.address.setCity(...)`, original có thể thay city không?  
**Đáp án:** Có nếu Address reference được share.

**Câu 7.** Một API lưu `byte[]` input để tính checksum lâu dài nên làm gì?  
**Đáp án:** Defensive-copy input nếu cần snapshot độc lập và caller còn alias.

**Câu 8.** Constructor clone input array, getter trả internal array: đã bảo vệ hai chiều chưa?  
**Đáp án:** Chưa, getter vẫn lộ mutable alias; nên trả copy nếu contract yêu cầu.

**Câu 9.** `new ArrayList<>(source)` copy element objects không?  
**Đáp án:** Không, nó copy element references.

**Câu 10.** `List.copyOf(source)` tạo deep immutable graph không?  
**Đáp án:** Không; cấu trúc unmodifiable nhưng mutable elements có thể shared.

**Câu 11.** `Collections.unmodifiableList(source)` có cam kết giữ snapshot khi source add không?  
**Đáp án:** Không; thường là unmodifiable live view.

**Câu 12.** `List.copyOf` có luôn tạo list identity mới không?  
**Đáp án:** Không, có thể tái sử dụng một unmodifiable input list phù hợp.

**Câu 13.** `record Snapshot(int[] bytes)` có tự clone mảng không?  
**Đáp án:** Không. Cần defensive copies nếu muốn độc lập.

**Câu 14.** Shallow-copy `List<MutableItem>` thì item rename qua source có hiện ở copy không?  
**Đáp án:** Có nếu cùng Item references.

**Câu 15.** Nếu muốn giữ báo giá cố định từ Product mutable, copy cả Product hay chụp Price value?  
**Đáp án:** Thường chụp immutable SKU/price/quantity values theo hợp đồng cần giữ.

**Câu 16.** Vì sao snapshot không tự atomically nhất quán nếu source bị mutate đồng thời?  
**Đáp án:** Nhiều lần đọc mutable fields có thể thấy các thời điểm khác nhau; cần synchronization/transaction.

**Câu 17.** Java có tự vô hiệu reference cũ sau “transfer ownership” không?  
**Đáp án:** Không, transfer thường là convention/protocol.

**Câu 18.** Clone Node A mà child có backlink về A thì backlink tự đổi thành copy A không?  
**Đáp án:** Không, trừ khi copy graph logic cập nhật edge.

**Câu 19.** Vì sao graph có cycles nên dùng `IdentityHashMap` khi clone deep?  
**Đáp án:** Memo theo identity giúp không clone lặp nodes, tránh recursion cycles và giữ shared-edge structure.

**Câu 20.** Copy wrapper chứa socket có tạo socket khác không?  
**Đáp án:** Không. Resource còn shared nếu wrapper chỉ copy reference.

**Câu 21.** Nếu hai viewers cùng `AtomicInteger`, giá trị có live không?  
**Đáp án:** Có, cả hai quan sát cùng shared mutable counter.

**Câu 22.** Nếu lưu `CounterSnapshot(int)`, counter thay có sửa snapshot không?  
**Đáp án:** Không; primitive value được chụp tại thời điểm tạo.

**Câu 23.** `volatile Config current` với immutable Config giải quyết điều gì?  
**Đáp án:** Publication/visibility của reference version; không tự ngăn lost updates của nhiều writers.

**Câu 24.** `new HashMap<>(source)` có deep-copy mutable keys không?  
**Đáp án:** Không, key references còn shared; phải giữ key state/equality/hash ổn định.

**Câu 25.** Vì sao `record ProductKey(String sku)` thường tốt hơn Product mutable làm key?  
**Đáp án:** Key value ổn định nếu SKU là identity phù hợp, không đổi theo Product.price/status.

**Câu 26.** Copy mọi immutable `Task` records trước khi đưa vào list mới có bắt buộc không?  
**Đáp án:** Không; có thể chia sẻ immutable elements an toàn về mutation.

**Câu 27.** Nếu task lớn và cập nhật thường xuyên, copy toàn bộ list mỗi lần có cost gì?  
**Đáp án:** Có thể O(n) mỗi update và tăng GC pressure; cân nhắc persistent structures/workload.

**Câu 28.** Một mutable builder có thể tạo immutable Plan versions khác nhau không?  
**Đáp án:** Có, nếu Plan chụp structure/values ở build boundary.

**Câu 29.** Để biết một API copy đúng, chỉ kiểm tra `equals` đủ không?  
**Đáp án:** Không. Cần kiểm tra outer/child identities và mutation isolation/sharing theo contract.

**Câu 30.** Chọn cách sao chép dựa trên nguyên tắc nào?  
**Đáp án:** **Copy đúng những mutable values cần ownership độc lập; share những immutable values hoặc live resources có contract rõ.**

## 33. Tài liệu tham khảo

- Java Language Specification (Java SE 17), [`4.3 — Reference Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.3): references và objects.
- Java Language Specification, [`15.26 — Assignment Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.26): assignment semantics.
- Java Language Specification, [`10.7 — Array Members](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html#jls-10.7): array clone và members.
- Java Language Specification, [`8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): generated record components/accessors.
- Java Language Specification, [`17.4 — Memory Model](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4): concurrency/happens-before.
- Java Language Specification, [`17.5 — final Field Semantics](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5): correctly constructed final fields.
- Java API Java SE 17, [`Object.clone()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#clone()): cloning contract và shallow copying.
- Java API, [`Cloneable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Cloneable.html): marker interface.
- Java API, [`List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable snapshot structure.
- Java API, [`Map.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)): unmodifiable map snapshot.
- Java API, [`Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): backed unmodifiable view.
- Java API, [`ArrayList(Collection)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#%3Cinit%3E(java.util.Collection)): copy cấu trúc list.
- Java API, [`IdentityHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html): object-reference identity cho graph memoization.
- Java API, [`AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomic shared mutable counter.
- Java API, [`HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): key equality/hash.
- Java API, [`AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): resource lifecycle.

## Kết luận

**Không có “sao chép tốt nhất” độc lập với ownership và mutability.** Gán reference không tạo object mới. Shallow copy tách outer structure nhưng có thể chia sẻ mutable components. Selective deep copy hoặc immutable snapshot tách **những giá trị cần giữ độc lập**, trong khi có thể tiếp tục chia sẻ immutable String/record/LocalDate components.

Trước mọi copy, hỏi **ai sở hữu**, **ai còn giữ alias**, **ai có quyền mutate**, **người nhận muốn live state hay snapshot**, và **dữ liệu cần sống bao lâu**. Chọn defensive copy ở input/output boundaries khi cần bảo vệ mutable representation; với graph có cycles giữ identity/sharing logic; với resources định nghĩa owner chịu trách nhiệm close. Trong concurrency, immutable values hữu ích nhưng publication và mutable holder vẫn cần coordination riêng.

Thiết kế tốt thường là **mutable trong phạm vi ownership hẹp, immutable khi xuất dữ liệu để chia sẻ**, và **copy tối thiểu nhưng đủ để giữ đúng hợp đồng**. Hãy kiểm thử bằng object identity `==`, state sau mutation và những tình huống aliasing/nested structures, không chỉ dựa vào tên `copy`, `clone` hay lời hứa “deep”.
