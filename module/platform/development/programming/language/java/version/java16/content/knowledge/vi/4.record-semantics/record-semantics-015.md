# Bất biến sâu, xuất bản an toàn và giới hạn thread safety của record

**Module:** `JAVA_VERSION_JAVA16`  
**Chương:** Ngữ nghĩa record  
**Áp dụng:** Java 16 trở lên, bao gồm Java hiện đại.

Record được thiết kế để mang dữ liệu. Các trường ứng với record component là `final`, vì vậy tham chiếu được lưu không thể được gán sang object khác sau khi khởi tạo. Nhưng điều đó **không tự làm object được tham chiếu trở nên bất biến**, không bảo đảm toàn bộ object graph bất biến sâu và cũng không tự làm mọi thao tác trên record thread-safe.

Để chia sẻ record an toàn giữa nhiều thread, cần xem xét ba lớp vấn đề:

1. **Bất biến sâu:** component và mọi object có thể truy cập từ component có bị thay đổi ngoài ý muốn không?
2. **Xuất bản an toàn:** thread khác nhận được tham chiếu record qua cơ chế nào và nhìn thấy trạng thái khởi tạo ra sao?
3. **Thread safety:** sau khi chia sẻ, các thao tác đọc/ghi trên component có được bảo vệ và phối hợp đúng không?

Record bất biến sâu, được khởi tạo đúng và xuất bản an toàn là một cách rất tốt để chia sẻ snapshot dữ liệu chỉ đọc. Tuy nhiên, từ khóa `record` tự nó không cung cấp các bảo đảm đó cho component mutable.

## 1. Trường final component chỉ cố định tham chiếu

Xét record chứa danh sách:

```java
import java.util.ArrayList;
import java.util.List;

record SearchState(List<String> filters) {}

List<String> source = new ArrayList<>(List.of("active"));
SearchState state = new SearchState(source);

source.add("premium");
System.out.println(state.filters()); // [active, premium]
```

Trường `filters` của record là `final`, nhưng nó đang giữ tham chiếu đến một `ArrayList` có thể thay đổi. Khi mã bên ngoài sửa danh sách nguồn, record quan sát được thay đổi đó.

Phân biệt ba khái niệm:

- **Final reference:** tham chiếu trong trường không thể được gán lại.
- **Shallow immutability:** trạng thái trực tiếp của object có thể không thay đổi, nhưng object mà nó tham chiếu tới vẫn có thể mutable.
- **Deep immutability:** toàn bộ trạng thái có thể truy cập từ object không thể bị thay đổi sau khi được tạo, theo hợp đồng của kiểu dữ liệu.

Record bảo đảm các trường component là final. Việc có đạt deep immutability hay không phụ thuộc vào kiểu component và cách constructor/accessor bảo vệ dữ liệu.

## 2. Sao chép collection để tạo snapshot cấu trúc

Với danh sách chứa phần tử immutable như `String`, có thể tạo snapshot độc lập trong compact constructor:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

record SearchState(List<String> filters) {
    SearchState {
        filters = List.copyOf(
            new ArrayList<>(
                Objects.requireNonNull(filters, "filters")
            )
        );
    }
}

List<String> source = new ArrayList<>(List.of("active"));
SearchState state = new SearchState(source);

source.add("premium");
System.out.println(state.filters()); // [active]
```

Constructor tạo một bản sao cấu trúc trước, sau đó tạo danh sách không thể sửa. Accessor tự sinh trả về danh sách snapshot đó. Vì phần tử là `String` immutable, nội dung quan sát được của record không bị thay đổi qua tham chiếu đầu vào.

Có một chi tiết đáng chú ý: `List.copyOf(collection)` có thể tái sử dụng collection đầu vào nếu nó đã là một danh sách không thể sửa. Một wrapper như `Collections.unmodifiableList(source)` không cho sửa qua wrapper, nhưng vẫn phản ánh thay đổi nếu nơi khác sửa `source`. Nếu yêu cầu là snapshot độc lập với mọi collection đầu vào, tạo bản sao như `new ArrayList<>(input)` trước khi gọi `List.copyOf`.

Ví dụ view không thể sửa nhưng vẫn bị ảnh hưởng bởi nguồn:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<String> source = new ArrayList<>(List.of("active"));
List<String> view = Collections.unmodifiableList(source);

source.add("premium");
System.out.println(view); // [active, premium]
```

Vì vậy, “không thể sửa qua accessor” và “không bị thay đổi qua bất kỳ alias nào” là hai yêu cầu khác nhau.

## 3. Sao chép nông không bảo vệ object mutable bên trong

Ngay cả khi đã tạo snapshot danh sách, các phần tử bên trong vẫn có thể mutable:

```java
import java.util.List;

final class MutableTag {
    private String name;

    MutableTag(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }

    void rename(String newName) {
        name = newName;
    }
}

record TagCollection(List<MutableTag> tags) {
    TagCollection {
        tags = List.copyOf(tags);
    }
}

MutableTag tag = new MutableTag("java");
TagCollection collection = new TagCollection(List.of(tag));

tag.rename("records");
System.out.println(collection.tags().get(0).name()); // records
```

`List.copyOf` bảo vệ cấu trúc danh sách, nhưng vẫn giữ tham chiếu đến cùng object `MutableTag`. Khi object đó đổi trạng thái, record cũng quan sát thấy thay đổi.

Nếu record cần đại diện cho một snapshot bất biến, hãy chuyển phần tử sang kiểu bất biến hoặc sao chép sâu theo mô hình dữ liệu. Ví dụ:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

record TagSnapshot(String name) {}

record TagCollection(List<TagSnapshot> tags) {
    TagCollection {
        tags = List.copyOf(new ArrayList<>(
            Objects.requireNonNull(tags, "tags")
        ));
    }
}

List<MutableTag> source =
    new ArrayList<>(List.of(new MutableTag("java")));

List<TagSnapshot> snapshots = source.stream()
    .map(tag -> new TagSnapshot(tag.name()))
    .toList();

TagCollection collection = new TagCollection(snapshots);
source.get(0).rename("records");

System.out.println(collection.tags()); // [TagSnapshot[name=java]]
```

`TagSnapshot` chỉ chứa `String` immutable. Thông tin được copy thành giá trị riêng nên thay đổi object nguồn không làm thay đổi snapshot. `Stream.toList()` có từ Java 16 và trả về danh sách không thể sửa; constructor vẫn tự tạo snapshot theo hợp đồng của record.

Không có một thao tác clone sâu tổng quát phù hợp cho mọi object graph. Khi sao chép sâu, cần xác định cách xử lý object dùng chung, chu trình tham chiếu, kiểu immutable, object không thể sao chép và các quan hệ identity cần giữ.

## 4. Mảng cũng cần sao chép phòng vệ

Mảng là mutable. Nếu record giữ trực tiếp mảng đầu vào, mã gọi có thể thay đổi nội dung sau khi tạo record:

```java
record Packet(byte[] payload) {}

byte[] source = {1, 2, 3};
Packet packet = new Packet(source);

source[0] = 99;
System.out.println(packet.payload()[0]); // 99
```

Để tạo snapshot độc lập, sao chép mảng trong constructor và trả bản sao từ accessor:

```java
import java.util.Objects;

record Packet(byte[] payload) {
    Packet {
        payload = Objects.requireNonNull(payload, "payload").clone();
    }

    public byte[] payload() {
        return payload.clone();
    }
}
```

Constructor bảo vệ khỏi thay đổi qua tham chiếu đầu vào; accessor bảo vệ khỏi thay đổi qua tham chiếu đầu ra. Mảng nội bộ không bị lộ trực tiếp.

Với mảng lồng nhau như `int[][]`, `clone()` trên mảng ngoài chỉ sao chép nông. Cần sao chép từng mảng con nếu muốn snapshot sâu. Nếu mảng là component của value record và equality phải dựa trên nội dung, còn cần tùy chỉnh đồng bộ `equals`/`hashCode` bằng `Arrays.equals`/`Arrays.hashCode` hoặc cặp deep tương ứng. Defensive copy không tự thay đổi equality mặc định của mảng.

## 5. Record không tự làm component thread-safe

Một record có thể chứa `ArrayList`, `HashMap` hoặc object mutable bất kỳ. Từ khóa `record` không thêm khóa đồng bộ, không biến collection thành concurrent collection và không tự ngăn các thread cùng sửa trạng thái.

Ví dụ không an toàn:

```java
import java.util.ArrayList;
import java.util.List;

record SharedState(List<String> events) {}

List<String> events = new ArrayList<>();
SharedState state = new SharedState(events);

// Thread A
state.events().add("started");

// Thread B
int count = state.events().size();
```

Nếu hai thread truy cập cùng `ArrayList` mà không có cơ chế phối hợp, việc đọc/ghi đồng thời không được bảo đảm an toàn. Có thể quan sát trạng thái không nhất quán hoặc gặp lỗi trong quá trình duyệt/sử dụng collection. Trường component `final` chỉ bảo đảm tham chiếu `events` không bị gán lại; nó không đồng bộ các thao tác trên danh sách.

Nếu cần dữ liệu snapshot chỉ đọc, hãy dùng component immutable và không cung cấp alias mutable. Nếu cần trạng thái thay đổi đồng thời, chọn cấu trúc dữ liệu concurrent hoặc một class có trách nhiệm đồng bộ hóa rõ ràng.

## 6. Final-field semantics không đồng nghĩa thread safety toàn diện

Java Memory Model có quy tắc đặc biệt cho final field. Khi object được khởi tạo đúng cách, các thread quan sát object có bảo đảm đặc biệt về giá trị các trường final sau khi constructor hoàn tất. Với final reference, quy tắc này còn liên quan đến trạng thái được khởi tạo trước thời điểm hoàn tất constructor của object mà reference trỏ tới.

Điều đó hữu ích cho record vì các trường component là final. Tuy nhiên, không nên suy rộng thành “mọi thứ mà record tham chiếu đều thread-safe”:

- Quy tắc final-field bảo vệ việc quan sát trạng thái khởi tạo đúng cách; nó không làm các thao tác mutable sau constructor trở nên an toàn.
- Nó không làm `ArrayList` hoặc `HashMap` thành cấu trúc concurrent.
- Nó không bảo đảm các cập nhật sau khi object được tạo sẽ tự động hiển thị nhất quán cho thread khác.
- Nó không làm một chuỗi thao tác gồm nhiều bước trở thành atomic.
- Nó không ngăn data race trên trạng thái mutable được chia sẻ.

Không để `this` thoát ra ngoài trong lúc constructor đang chạy. Ví dụ không đăng ký listener, đưa `this` vào static field hoặc gọi callback có thể công bố object trước khi các component được thiết lập đầy đủ. Với record, constructor tùy chỉnh vẫn cần tuân thủ nguyên tắc khởi tạo an toàn này.

## 7. Xuất bản an toàn một record bất biến

Khi nhiều thread cần đọc cùng một snapshot, hãy dùng cơ chế xuất bản an toàn. Những cách phổ biến gồm:

- Gán vào trường `volatile`.
- Gán hoặc đọc dưới cùng một `synchronized` lock.
- Khởi tạo qua static initializer hoặc static final field.
- Đưa vào một concurrent collection hoặc cơ chế truyền task có bảo đảm memory-consistency phù hợp.
- Dùng `AtomicReference` khi cần thay thế snapshot hoặc cập nhật tham chiếu nguyên tử.

Ví dụ dùng `volatile` để công bố một snapshot chỉ đọc:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

record CatalogSnapshot(List<String> products) {
    CatalogSnapshot {
        products = List.copyOf(
            new ArrayList<>(Objects.requireNonNull(products))
        );
    }
}

final class CatalogStore {
    private volatile CatalogSnapshot current =
        new CatalogSnapshot(List.of());

    CatalogSnapshot current() {
        return current;
    }

    void publish(CatalogSnapshot next) {
        current = Objects.requireNonNull(next);
    }
}
```

Writer tạo một snapshot mới rồi gán vào trường volatile. Reader đọc tham chiếu qua cùng trường volatile. Việc ghi volatile *happens-before* các lần đọc volatile tương ứng sau đó, giúp công bố trạng thái đã khởi tạo. Vì snapshot và danh sách của nó không thể thay đổi qua alias, nhiều reader có thể đọc đồng thời mà không cần khóa cho từng lần đọc.

`volatile` chỉ bảo vệ việc đọc/ghi tham chiếu và thứ tự hiển thị theo memory model; nó không biến một component mutable bên trong thành thread-safe. Nếu `CatalogSnapshot` giữ `ArrayList` mutable có alias khác, vấn đề vẫn còn.

## 8. Dùng AtomicReference để thay thế snapshot

Khi cần cập nhật dựa trên snapshot trước đó, `AtomicReference` cung cấp các thao tác nguyên tử trên tham chiếu:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

record InventorySnapshot(Map<String, Integer> quantities) {
    InventorySnapshot {
        quantities = Map.copyOf(quantities);
    }
}

AtomicReference<InventorySnapshot> current =
    new AtomicReference<>(
        new InventorySnapshot(Map.of("SKU-1", 10))
    );

current.updateAndGet(previous -> {
    Map<String, Integer> next =
        new HashMap<>(previous.quantities());
    next.put("SKU-1", next.get("SKU-1") - 1);
    return new InventorySnapshot(next);
});
```

Mỗi lần cập nhật tạo một map mới và một record snapshot mới. `updateAndGet` thay thế tham chiếu nguyên tử; reader lấy một snapshot nhất quán tại thời điểm đọc.

Hàm truyền vào `updateAndGet` có thể được gọi lại khi có tranh chấp cập nhật. Vì vậy, giữ hàm cập nhật không có side effect bên ngoài; không gửi email, ghi file hoặc tăng một bộ đếm ngoài trong lambda rồi giả định lambda chỉ chạy một lần.

`Map.copyOf` tạo map không thể sửa qua API map. Ví dụ này an toàn vì khóa `String` và giá trị `Integer` là immutable. Nếu map chứa value mutable, cần snapshot hoặc đồng bộ hóa các value đó riêng.

## 9. Khi nào dùng concurrent component thay cho snapshot?

Không phải hệ thống nào cũng phù hợp với mô hình snapshot bất biến. Nếu nghiệp vụ cần nhiều thread cùng cập nhật một cấu trúc dữ liệu, hãy chọn một abstraction được thiết kế cho cập nhật đồng thời:

| Nhu cầu | Hướng thiết kế |
| --- | --- |
| Nhiều thread đọc cùng một cấu hình ít thay đổi | Record snapshot bất biến, công bố bằng `volatile` hoặc `AtomicReference`. |
| Nhiều thread cập nhật map theo từng khóa | Dùng `ConcurrentHashMap` và xác định rõ atomicity cần thiết cho từng thao tác. |
| Cập nhật một bộ đếm | Dùng `AtomicInteger`, `LongAdder` hoặc cơ chế đồng bộ phù hợp với yêu cầu. |
| Nhiều thao tác phải cùng thành công/thất bại | Dùng một lock hoặc transaction/abstraction có atomicity phù hợp; không giả định nhiều lời gọi concurrent tự tạo thành một transaction. |
| Muốn lưu lịch sử bất biến theo từng phiên bản | Tạo record snapshot mới cho mỗi phiên bản và công bố tham chiếu mới. |

Có thể đặt một concurrent object bên trong record, nhưng cần hiểu equality của component đó, quyền sở hữu và cách thao tác được đồng bộ. Record chỉ mang tham chiếu; nó không tự cung cấp chính sách cập nhật.

## 10. An toàn khi chia sẻ khác với bất biến nghiệp vụ

Một object có thể thread-safe nhưng vẫn mutable. Ví dụ collection concurrent có thể cho phép nhiều thread cập nhật an toàn, nhưng nội dung của nó vẫn thay đổi theo thời gian. Ngược lại, một record có component immutable nhưng được truy cập qua một đường công bố không phù hợp vẫn cần xem xét memory visibility và vòng đời tham chiếu.

Phân biệt:

- **Immutable:** trạng thái không thay đổi sau khi tạo.
- **Thread-safe:** các thao tác đồng thời tuân thủ hợp đồng của abstraction.
- **Safely published:** thread nhận được tham chiếu theo cơ chế có bảo đảm visibility và ordering phù hợp.
- **Atomic:** thao tác được quan sát như một đơn vị không thể bị xen giữa theo hợp đồng của API.

Các khái niệm này liên quan nhưng không thay thế nhau. Với record snapshot, mục tiêu thường là immutable + safe publication để nhiều thread chỉ đọc. Với cấu trúc cập nhật liên tục, cần concurrent abstraction hoặc đồng bộ hóa phù hợp.

## 11. Những nhầm lẫn cần tránh

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| Component là `final` nên object bên trong không thể thay đổi. | **Sai** | `final` cố định tham chiếu, không đóng băng object được tham chiếu. |
| `List.copyOf` tự sao chép sâu mọi phần tử. | **Sai** | Nó bảo vệ cấu trúc danh sách, không clone phần tử mutable. |
| `Collections.unmodifiableList` luôn là snapshot độc lập. | **Sai** | Wrapper có thể phản ánh thay đổi từ collection nguồn. |
| Record tự làm `ArrayList` thread-safe. | **Sai** | Các thao tác trên component vẫn theo hợp đồng của `ArrayList`. |
| Final-field semantics làm mọi cập nhật sau constructor hiển thị an toàn. | **Sai** | Nó không đồng bộ các mutation về sau. |
| Snapshot immutable được công bố bằng `volatile` phù hợp cho nhiều reader. | **Đúng** | Ghi/đọc volatile thiết lập quan hệ happens-before; snapshot phải thật sự không mutable qua alias. |
| `AtomicReference` làm object được tham chiếu tự thread-safe. | **Sai** | Nó bảo vệ thao tác trên tham chiếu; trạng thái object vẫn cần thiết kế riêng. |
| Record có thể chứa một concurrent component. | **Đúng** | Nhưng quyền sở hữu, equality và thao tác concurrent vẫn phải được xác định. |

## 12. Checklist thiết kế record dùng giữa nhiều thread

1. Component nào immutable, component nào mutable?
2. Có alias bên ngoài nào còn giữ quyền sửa object được record tham chiếu tới không?
3. Collection đã được snapshot độc lập chưa, kể cả trường hợp đầu vào là unmodifiable view?
4. Phần tử bên trong collection có mutable không? Có cần chuyển thành immutable snapshot hoặc sao chép sâu không?
5. Array đã được sao chép ở constructor và accessor chưa?
6. Constructor có để `this` thoát ra ngoài trước khi khởi tạo hoàn tất không?
7. Record được công bố qua `volatile`, lock, static initialization, concurrent collection hay cơ chế nào?
8. Các mutation sau khi công bố có được đồng bộ hoặc thay bằng snapshot mới không?
9. Có cần atomic update nhiều trường như một đơn vị không?
10. Nếu dùng `AtomicReference` update function, hàm có tránh side effect vì có thể được gọi lại không?
11. Equality/hash của record có phụ thuộc vào component mutable không?
12. Mô hình phù hợp là snapshot immutable hay một concurrent object có vòng đời cập nhật?

**Ghi nhớ:** Record chỉ làm final các tham chiếu component. Muốn chia sẻ an toàn, hãy tạo dữ liệu bất biến sâu bằng snapshot và defensive copy, không để alias mutable thoát ra ngoài, khởi tạo object đúng cách và công bố qua cơ chế memory-consistency phù hợp. Nếu trạng thái cần cập nhật đồng thời, dùng concurrent abstraction hoặc đồng bộ hóa rõ ràng; record tự nó không làm component thread-safe.

## Tài liệu chính thức

- [Java Language Specification, Section 8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.10).
- [Java Language Specification, Section 17.5 — Final Field Semantics](https://docs.oracle.com/javase/specs/jls/se26/html/jls-17.html#jls-17.5).
- [Java Language Specification, Section 17.4.5 — Happens-before Order](https://docs.oracle.com/javase/specs/jls/se26/html/jls-17.html#jls-17.4.5).
- [Java SE 26 API — `java.util.List.copyOf`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).
- [Java SE 26 API — `java.util.concurrent.atomic.AtomicReference`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html).
- [JEP 395 — Records, tính năng chính thức trong Java 16](https://openjdk.org/jeps/395).
