# Không dựa vào identity hoặc dùng danh sách kết quả làm khóa đồng bộ

`Stream.toList()` trả về một danh sách không sửa đổi được (*unmodifiable List*). Javadoc còn nêu rõ danh sách kết quả có thể là *value-based*: chương trình không được giả định mỗi lần gọi sẽ tạo một object có identity riêng hoặc ổn định. Vì vậy, tránh so sánh hai kết quả bằng `==`, lấy `System.identityHashCode()` làm mã định danh, hoặc dùng chính danh sách làm monitor cho `synchronized`.

Khi cần so sánh nội dung, hãy dùng `equals()`. Khi cần đồng bộ truy cập trạng thái dùng chung, hãy tạo một object khóa riêng do ứng dụng sở hữu. Nếu dùng danh sách làm khóa trong `HashMap`, hãy dựa trên `equals()`/`hashCode()` và bảo đảm nội dung tham gia tính hash không thay đổi trong thời gian danh sách nằm trong map.

## 1. Value-based nghĩa là gì trong trường hợp `Stream.toList()`?

Hợp đồng của `Stream.toList()` quy định kiểu trả về là `List<T>` không sửa đổi được. Javadoc cho phép implementation trả về một danh sách value-based và yêu cầu caller không đưa ra giả định về identity của object kết quả.

Điều này có nghĩa chương trình nên xem kết quả như một giá trị được sử dụng theo nội dung của nó. API không bảo đảm identity của object qua các lần gọi; mã nguồn không nên phụ thuộc vào việc hai biến có cùng tham chiếu hay không.

```java
import java.util.List;
import java.util.stream.Stream;

List<String> first = Stream.of("An", "Bình").toList();
List<String> second = Stream.of("An", "Bình").toList();

// Không dựa vào kết quả của phép so sánh này:
boolean sameReference = first == second;

// So sánh nội dung theo hợp đồng của List:
boolean sameContents = first.equals(second);

System.out.println(sameContents); // true
```

`List.equals()` so sánh các phần tử theo thứ tự. Nếu hai danh sách có cùng số phần tử và từng cặp phần tử tương ứng bằng nhau theo `equals()`, hai danh sách được xem là bằng nhau.

Việc kiểm tra null như `result == null` vẫn là kiểm tra null thông thường. Điều cần tránh là dùng `==` để quyết định hai object kết quả có phải cùng một instance hay không.

## 2. Tránh dùng `==` để so sánh hai danh sách kết quả

`==` trên hai biến tham chiếu kiểm tra chúng có trỏ tới cùng một object hay không. Nó không so sánh nội dung danh sách.

```java
import java.util.List;

List<String> namesA = List.of("Java", "Stream").stream().toList();
List<String> namesB = List.of("Java", "Stream").stream().toList();

if (namesA.equals(namesB)) {
    System.out.println("Hai danh sách có cùng nội dung");
}
```

Nếu mục tiêu là kiểm tra nội dung, `equals()` diễn đạt chính xác ý định và không phụ thuộc identity của object. Không viết logic cache, kiểm tra trùng lặp hoặc quyết định nghiệp vụ dựa trên `first == second` với danh sách trả về từ `toList()`.

Nếu ứng dụng thật sự cần nhận diện một lần tạo dữ liệu cụ thể, hãy tạo một định danh riêng, chẳng hạn `UUID`, hoặc một object token do ứng dụng quản lý. Đừng dùng chính danh sách value-based làm định danh phiên bản hay định danh lần tạo.

## 3. Phân biệt `hashCode()` với `System.identityHashCode()`

Hai phương thức có mục đích khác nhau:

| API | Ý nghĩa | Khi sử dụng |
| --- | --- | --- |
| `list.hashCode()` | Hash theo hợp đồng của `List`, nhất quán với `equals()` | Cấu trúc dữ liệu dựa trên giá trị như `HashMap` và `HashSet`. |
| `System.identityHashCode(list)` | Hash dựa trên identity của object, không phụ thuộc việc override `hashCode()` | Không dùng làm mã định danh ổn định cho kết quả `Stream.toList()`. |

Ví dụ, có thể dùng `hashCode()` để kiểm tra tính nhất quán với `equals()`:

```java
import java.util.List;

List<String> first = List.of("An", "Bình").stream().toList();
List<String> second = List.of("An", "Bình").stream().toList();

System.out.println(first.equals(second));
System.out.println(first.hashCode() == second.hashCode());
```

Nếu hai danh sách bằng nhau theo `equals()`, chúng phải có cùng `hashCode()`. Chiều ngược lại không được bảo đảm: hai danh sách có cùng hash vẫn có thể khác nội dung.

Không dùng `System.identityHashCode()` để tạo cache key, ID nghiệp vụ hoặc để xác định một danh sách có phải bản cũ hay không. Giá trị này không phải ID duy nhất và không thay thế một định danh do ứng dụng quản lý.

## 4. Có thể dùng danh sách làm khóa `HashMap` không?

Có thể dùng danh sách làm khóa trong cấu trúc dựa trên giá trị như `HashMap`, vì `HashMap` sử dụng `equals()` và `hashCode()`, không dùng identity của khóa. Điều kiện là nội dung ảnh hưởng đến `equals()`/`hashCode()` phải ổn định trong suốt thời gian danh sách được dùng làm khóa.

Ví dụ với phần tử `String` immutable:

```java
import java.util.HashMap;
import java.util.List;
import java.util.Map;

List<String> key = List.of("An", "Bình").stream().toList();

Map<List<String>, String> labels = new HashMap<>();
labels.put(key, "Nhóm A");

String label = labels.get(List.of("An", "Bình"));
System.out.println(label); // Nhóm A
```

Lookup thành công vì danh sách truy vấn bằng danh sách khóa theo `List.equals()` và có cùng `hashCode()`. Không cần hai biến tham chiếu tới cùng một object.

Tuy nhiên, danh sách unmodifiable chỉ ngăn thay đổi cấu trúc. Nếu phần tử là object mutable và `equals()`/`hashCode()` của phần tử phụ thuộc vào trạng thái có thể thay đổi, hash của danh sách cũng có thể thay đổi. Khi đó map có thể không tìm lại được khóa ở bucket ban đầu.

Ví dụ về tình huống cần tránh:

```java
import java.util.HashMap;
import java.util.List;
import java.util.Map;

class MutableKey {
    private String name;

    MutableKey(String name) { this.name = name; }
    void setName(String name) { this.name = name; }

    @Override
    public boolean equals(Object other) {
        return other instanceof MutableKey that && name.equals(that.name);
    }

    @Override
    public int hashCode() { return name.hashCode(); }
}

class MutableListKeyExample {
    public static void main(String[] args) {
        List<MutableKey> source = List.of(new MutableKey("An"));
        List<MutableKey> key = source.stream().toList();
        Map<List<MutableKey>, String> map = new HashMap<>();

        map.put(key, "Giá trị");
        key.get(0).setName("Tên mới");

        // Hash của key đã đổi; map có thể không tìm lại được entry.
        System.out.println(map.get(key));
    }
}
```

Nếu cần dùng danh sách làm khóa, hãy ưu tiên phần tử immutable hoặc tạo một key snapshot chỉ chứa giá trị immutable. Đừng nhầm tính unmodifiable của danh sách với tính bất biến sâu của toàn bộ phần tử.

## 5. Không dùng danh sách kết quả làm monitor cho `synchronized`

Không viết:

```java
import java.util.List;

List<String> source = List.of("An", "Bình");
List<String> result = source.stream().toList();

synchronized (result) {
    // Đồng bộ hóa dựa trên identity của danh sách value-based
}
```

Javadoc cảnh báo các thao tác nhạy cảm với identity, bao gồm synchronization, không đáng tin cậy trên object value-based và cần tránh. Ngoài ra, đồng bộ hóa trên một danh sách unmodifiable không tự làm các object phần tử mutable trở nên thread-safe.

Vấn đề lớn khi dùng object dữ liệu làm monitor là mọi bên tham gia phải khóa đúng cùng một object. Nếu implementation được phép thay đổi identity hoặc tái sử dụng instance, code đồng bộ dựa trên identity của kết quả không có hợp đồng ổn định.

Hãy tạo một lock object riêng:

```java
import java.util.List;

class NameRegistry {
    private final Object stateLock = new Object();
    private List<String> snapshot = List.of();

    void replace(List<String> source) {
        List<String> next = source.stream().toList();

        synchronized (stateLock) {
            snapshot = next;
        }
    }

    List<String> snapshot() {
        synchronized (stateLock) {
            return snapshot;
        }
    }
}
```

`stateLock` là object riêng do `NameRegistry` sở hữu và có identity ổn định trong suốt vòng đời instance. Mọi lần đọc hoặc thay thế trường `snapshot` đều dùng cùng lock. Danh sách được trả ra là unmodifiable; trong ví dụ này phần tử là `String` immutable, nên caller có thể đọc snapshot sau khi phương thức trả về mà không cần khóa trên chính danh sách.

## 6. Khi cần khóa, hãy quản lý vòng đời và phạm vi của lock

Một lock nên có phạm vi sở hữu rõ ràng và không được đưa ra ngoài cho code không liên quan. Thông thường, dùng một field `private final Object` trong class quản lý trạng thái:

```java
class Inventory {
    private final Object lock = new Object();
    private int quantity;

    void add(int amount) {
        synchronized (lock) {
            quantity += amount;
        }
    }

    int quantity() {
        synchronized (lock) {
            return quantity;
        }
    }
}
```

Trong ví dụ này, `lock` bảo vệ trạng thái `quantity`. Không dùng một collection được trả về từ API làm monitor. Nếu class có nhiều nhóm trạng thái độc lập, có thể dùng lock riêng cho từng nhóm khi điều đó giúp giảm tranh chấp và vẫn giữ được tính nhất quán của dữ liệu.

Không tạo `new Object()` ngay tại mỗi câu lệnh `synchronized`; các thread cần phối hợp phải đồng bộ trên cùng một lock instance. Cũng không trả lock ra khỏi class, vì caller có thể vô tình hoặc cố ý làm thay đổi hành vi đồng bộ nội bộ.

## 7. Không dùng `IdentityHashMap` hoặc identity-based cache cho kết quả này

`IdentityHashMap` cố ý so sánh key bằng `==` thay vì `equals()`. Cấu trúc này phù hợp với một số bài toán cần identity object thật sự, chẳng hạn xử lý object graph theo tham chiếu. Nhưng danh sách từ `Stream.toList()` không cung cấp bảo đảm identity để dùng làm key theo cách đó.

Nếu mục tiêu là cache theo nội dung danh sách, dùng `HashMap` thông thường với key có `equals()`/`hashCode()` ổn định. Nếu mục tiêu là nhận diện lần tạo, hãy dùng một ID riêng. Chọn cấu trúc dữ liệu theo ngữ nghĩa cần thiết, không theo identity tình cờ của object collection.

## 8. Những điểm cần nhớ

- Kết quả `Stream.toList()` có thể là value-based; không giả định identity của các instance.
- Dùng `equals()` để so sánh nội dung danh sách, không dùng `==` giữa hai kết quả.
- `hashCode()` của `List` phù hợp với cấu trúc dựa trên giá trị; `System.identityHashCode()` không phải ID nghiệp vụ.
- Có thể dùng `List` làm key trong `HashMap` nếu các giá trị tham gia `equals()`/`hashCode()` ổn định.
- Unmodifiable chỉ bảo vệ cấu trúc list; object mutable bên trong vẫn có thể làm thay đổi kết quả `equals()`/`hashCode()`.
- Không dùng danh sách kết quả làm monitor cho `synchronized` hoặc key trong `IdentityHashMap`.
- Tạo lock riêng bằng `private final Object` và bảo đảm mọi thread dùng cùng lock để bảo vệ trạng thái chung.

Hãy xem danh sách từ `Stream.toList()` như một giá trị để đọc và so sánh theo nội dung. Nếu cần định danh hoặc đồng bộ hóa, hãy tạo cơ chế riêng có identity và vòng đời do ứng dụng kiểm soát. Cách này tránh phụ thuộc vào identity mà Java API không cam kết.

## Tài liệu tham khảo

- [Stream.toList() – Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/stream/Stream.html#toList())
- [Stream.toList() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html#toList())
- [List.equals() và List.hashCode() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html)
- [Object identity and synchronization – Java Language Specification, §17](https://docs.oracle.com/javase/specs/jls/se26/html/jls-17.html)
- [IdentityHashMap – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/IdentityHashMap.html)
