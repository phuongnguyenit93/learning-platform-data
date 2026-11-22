# `hashCode()` và cách dùng `record` làm khóa `Map` hoặc phần tử `Set` (Java 16+)

> Mục tiêu: hiểu `equals()`/`hashCode()` được Java sinh cho record, cách `HashMap` và `HashSet` xác định khóa hoặc phần tử trùng nhau, và thiết kế component đủ ổn định để tra cứu không bị sai khi dữ liệu có thể thay đổi. Record là tính năng **chính thức từ Java 16**, các ví dụ dùng cú pháp ổn định và chạy được trên JDK 17 trở lên; không cần chế độ preview của Java 14/15.

## 1. Vì sao `record` phù hợp cho khóa dữ liệu?

Với một class Java thông thường, nếu không viết `equals()` và `hashCode()`, hành vi kế thừa từ `Object` thường dựa trên danh tính đối tượng. Một `record` tự có hai phương thức dựa trên **toàn bộ record component**. Khi hai record cùng lớp có các component bằng nhau, chúng được coi là bằng nhau dù được tạo bằng hai lệnh `new` riêng.

```java
record Point(int x, int y) {}

Point p1 = new Point(2, 3);
Point p2 = new Point(2, 3);

System.out.println(p1 == p2);             // false: hai tham chiếu khác nhau.
System.out.println(p1.equals(p2));        // true: cùng kiểu và cùng component.
System.out.println(p1.hashCode() == p2.hashCode()); // true.
```

Đây là **đoạn minh họa đặt trong môi trường có thể khai báo record và câu lệnh**, chẳng hạn khai báo `Point` trong class rồi đặt ba câu lệnh trong `main`. Chương trình hoàn chỉnh ở mục 7.

Tự sinh `equals()`/`hashCode()` giúp biểu đạt một khóa tổ hợp như `record AccountKey(long tenantId, String username) {}`. Thay vì nối chuỗi `tenantId + ":" + username` với nguy cơ va chạm định dạng, ta có hai component được kiểm tra theo giá trị.

**Giới hạn quan trọng:** record chỉ **bất biến nông (shallowly immutable)**. Các field tương ứng component là `private final`, nghĩa là không gán lại tham chiếu field được, nhưng nếu một component tham chiếu tới `List`, `Date`, mảng hoặc đối tượng mutable khác thì nội dung đối tượng được tham chiếu vẫn có thể đổi. Điều này tác động trực tiếp đến khóa của bộ sưu tập băm.

## 2. Hợp đồng `equals()` và `hashCode()` mặc định

Với một record không tự override hai phương thức này, Java sinh chúng theo thành phần dữ liệu:

1. `equals(Object)` trả `true` khi đối tượng kia là **cùng lớp record** và **mọi component tương ứng bằng nhau**. Một record thuộc lớp khác dù các component trông giống hệt vẫn không bằng.
2. Với component kiểu tham chiếu, phép so sánh tương đương `Objects.equals(a, b)`: hai `null` bằng nhau; giá trị không null dựa vào `equals()` của chính kiểu component.
3. Với component nguyên thủy, phép so sánh tương đương `compare(...) == 0` của wrapper tương ứng (`Integer`, `Double`, `Float`, v.v.). Vì vậy với `double`, `-0.0` và `+0.0` được xem là **khác nhau**, còn hai giá trị `NaN` được xem là bằng nhau bởi quy tắc của `Double.compare`.
4. `hashCode()` tạo mã băm `int` từ các component sao cho **hai record bằng nhau thì luôn có cùng hash** trong điều kiện dữ liệu dùng cho equality vẫn ổn định.
5. Cách kết hợp hash của các component là **chi tiết triển khai không được bảo đảm**. Không giả định `record.hashCode()` luôn bằng `Objects.hash(...)`, không lưu số hash làm ID lâu dài hoặc dùng nó thay cho mã định danh nghiệp vụ.

**Hợp đồng tổng quát của hashing:**

- `a.equals(b) == true` **bắt buộc** kéo theo `a.hashCode() == b.hashCode()`.
- `a.hashCode() == b.hashCode()` **không** kéo theo `a.equals(b) == true`: va chạm hash là hợp lệ và các collection vẫn gọi `equals()` để phân biệt.
- Một khóa đã nằm trong cấu trúc băm phải có thông tin dùng cho `equals()`/`hashCode()` **ổn định** trong suốt thời gian nó làm khóa. Nếu trạng thái liên quan bị sửa, tra cứu có thể không còn tìm thấy entry.
- `hashCode()` là một số `int` phục vụ bảng băm, **không** phải hash mật mã, không bảo đảm duy nhất và không phải mã chống giả mạo.

Ví dụ với record kết hợp:

```java
record OrderKey(long storeId, String orderNo) {}

OrderKey k1 = new OrderKey(3L, "A100");
OrderKey k2 = new OrderKey(3L, "A100");
OrderKey k3 = new OrderKey(4L, "A100");

// k1.equals(k2) là true, nhưng k1.equals(k3) là false.
```

Hai key khác `storeId` phải khác nhau nếu store là một phần định danh. Không nên bỏ component quan trọng khỏi bản thiết kế khóa chỉ vì dữ liệu hiện tại chưa có trùng lặp.

## 3. `record` làm khóa `HashMap`

`HashMap<K,V>` dùng `hashCode()` của khóa để xác định vị trí tìm kiếm, rồi dùng `equals()` để nhận diện khóa tương đương trong trường hợp cần đối chiếu. Khi `put` với một khóa **bằng** khóa đã tồn tại, giá trị được thay thế; map vẫn có một entry cho khóa đó.

```java
record UserKey(long tenantId, String username) {}

Map<UserKey, String> names = new java.util.HashMap<>();
names.put(new UserKey(7, "alice"), "ACTIVE");

String found = names.get(new UserKey(7, "alice")); // "ACTIVE".
names.put(new UserKey(7, "alice"), "UPDATED");   // Thay giá trị.
int count = names.size();                         // 1.
```

Đây là **snippet minh họa**, cần `java.util.Map` hoặc import tương ứng và đặt các câu lệnh trong phương thức. Không có yêu cầu sử dụng cùng instance làm khóa tra cứu; một instance mới nhưng bằng theo `equals()` vẫn truy xuất được.

**Dùng record cho khóa ghép:** `record CacheKey(String environment, long accountId) {}` giúp tách rõ các chiều. Khi tạo key từ dữ liệu ngoài, hãy chuẩn hóa theo **đúng hợp đồng nghiệp vụ** (ví dụ username không phân biệt chữ hoa/thường), rồi giữ chính sách chuẩn hóa nhất quán ở nơi tạo record. Không tùy tiện `toLowerCase()` một mã vốn phân biệt chữ hoa/thường.

**`Map` không đồng nghĩa với HashMap:** `TreeMap` dùng `Comparator` hoặc `Comparable` để sắp xếp và xác định khóa tương đương theo phép so sánh; `record` không tự triển khai `Comparable`. Nếu dùng `TreeMap<OrderKey,V>`, cần cung cấp comparator có quan hệ nhất quán với mong muốn nhận diện key. `IdentityHashMap` lại dùng **định danh tham chiếu** thay vì `equals()`/`hashCode()` thông thường, nên không phải lựa chọn để tận dụng bình đẳng theo giá trị của record.

## 4. `record` làm phần tử `HashSet`

`HashSet<E>` dùng hợp đồng `hashCode()`/`equals()` để giữ **mỗi giá trị tương đương đúng một lần**. Cũng như map, các record bằng nhau không cần là cùng một instance.

```java
record Cell(int row, int column) {}

Set<Cell> visited = new java.util.HashSet<>();
visited.add(new Cell(2, 3)); // true.
visited.add(new Cell(2, 3)); // false: giá trị tương đương đã có.
visited.add(new Cell(3, 2)); // true: hai component khác vị trí.
System.out.println(visited.size()); // 2.
```

Nhờ đó `Set<Coordinate>` hoặc `Set<PermissionKey>` diễn tả tập những giá trị không lặp. Không dùng `==` khi kiểm tra tính duy nhất theo giá trị. `HashSet` **không bảo đảm thứ tự duyệt**, còn `LinkedHashSet` giữ thứ tự chèn; nếu cần tập sắp xếp, `TreeSet` cần cách so sánh. Record không tự đem lại thứ tự tự nhiên.

## 5. Bẫy quan trọng: `final` không làm component mutable trở nên bất biến

Giả sử dùng một `List` có thể sửa làm component:

```java
record UnsafeTags(java.util.List<String> tags) {}

java.util.List<String> source = new java.util.ArrayList<>();
source.add("reader");
UnsafeTags key = new UnsafeTags(source);
java.util.Map<UnsafeTags, String> cache = new java.util.HashMap<>();
cache.put(key, "FOUND");

source.add("writer"); // Đã sửa nội dung danh sách mà key đang tham chiếu.
```

Field `key.tags` vẫn trỏ tới **cùng một List**; Java không ngăn List thay đổi. `List.equals()`/`List.hashCode()` phụ thuộc nội dung phần tử, nên thay đổi List có thể làm thay đổi mã băm và kết quả so sánh của `UnsafeTags`. Nếu khóa đã được thêm vào `HashMap`/`HashSet`, thao tác tìm kiếm, xóa hoặc kiểm tra tồn tại có thể trở nên bất thường. Không phụ thuộc vào việc một JVM cụ thể có trả `null` trong một lần thử: đây là **lỗi thiết kế về tính ổn định của khóa**, không phải hành vi thất bại luôn cố định.

**Giải pháp khi phần tử là `String` bất biến:**

```java
record SafeTags(java.util.List<String> tags) {
    SafeTags {
        tags = java.util.List.copyOf(tags);
    }
}
```

Trong compact canonical constructor, `List.copyOf` tạo snapshot dưới dạng list không thể sửa qua API của list đó. Nguồn `List` thay đổi sau này sẽ không làm thay đổi danh sách mà record giữ. Với phần tử `String` bất biến, đây là một lựa chọn thích hợp cho key. `List.copyOf` từ chối list hoặc phần tử `null`; nếu `null` là giá trị hợp lệ theo hợp đồng dữ liệu, cần thiết kế cách biểu diễn và sao chép khác.

**Cảnh báo về sao chép nông:** `List.copyOf()` không sao chép sâu đối tượng nằm trong list. Nếu list chứa `StringBuilder`, một class mutable hoặc các phần tử có `equals()`/`hashCode()` thay đổi, khóa vẫn không ổn định. Cần chuyển phần tử thành giá trị bất biến, tạo bản sao sâu có chủ đích, hoặc chỉ lấy ID bất biến.

| Loại component | Dùng trực tiếp làm thành phần khóa? | Lưu ý |
|---|---|---|
| `int`, `long`, `boolean`, `String`, `UUID`, `LocalDate`, enum | Thường phù hợp | Những giá trị này ổn định; vẫn cần xác định đúng thành phần định danh |
| `List<String>` | Phù hợp nếu sao chép và không để sửa | `List.copyOf(...)` hoặc dữ liệu immutable tương đương |
| `List<MutableObject>` | Cẩn trọng | List không sửa không có nghĩa các phần tử không sửa |
| `byte[]`, `int[]`, các mảng khác | Không cho so sánh nội dung mặc định | Mảng dùng `equals()` từ `Object`, xem mục 6 |
| `Date`, `StringBuilder`, các đối tượng mutable | Tránh làm key trực tiếp | Nội dung có thể đổi hoặc equality/hash có thể không biểu diễn đúng giá trị nghiệp vụ |

## 6. Bẫy mảng: hai mảng giống nội dung vẫn có thể làm hai record không bằng nhau

Với khai báo sau, `data` là **mảng**, một kiểu tham chiếu có `equals()`/`hashCode()` mặc định dựa vào **định danh mảng**, không so sánh từng phần tử:

```java
record ArrayKey(byte[] data) {}

ArrayKey a = new ArrayKey(new byte[] {1, 2});
ArrayKey b = new ArrayKey(new byte[] {1, 2});

System.out.println(a.equals(b)); // false: hai mảng khác instance.
```

Vì thế `HashSet<ArrayKey>` có thể chứa cả `a` và `b` dù payload byte trùng nhau. `ArrayKey` cũng trả trực tiếp tham chiếu mảng qua accessor `data()`, cho phép bên ngoài thay nội dung; record không có cơ chế deep immutability tự động. `Arrays.equals` và `Arrays.hashCode` **không** được áp dụng tự động cho mảng trong synthesized record equality/hash.

**Nếu bắt buộc dùng giá trị mảng làm key**, có thể tạo một kiểu record bất biến về nội dung bằng cách (1) sao chép mảng đầu vào, (2) trả bản sao ở accessor, và (3) override cả `equals` lẫn `hashCode` theo nội dung. Ví dụ tệp `ByteValue.java`:

```java
import java.util.Arrays;
import java.util.Objects;

public record ByteValue(byte[] bytes) {
    public ByteValue {
        bytes = Objects.requireNonNull(bytes, "bytes").clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof ByteValue b
            && Arrays.equals(bytes, b.bytes);
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(bytes);
    }
}
```

Ví dụ này có thể biên dịch riêng bằng `javac -encoding UTF-8 ByteValue.java`. Hai `new ByteValue(new byte[] {1, 2})` sẽ bằng nhau và có cùng hash. Việc sửa mảng đầu vào sau constructor hoặc sửa mảng nhận được từ accessor không ảnh hưởng tới state bên trong record. Override **cả hai** phương thức là thiết yếu để giữ hợp đồng.

Thông thường nên ưu tiên key gồm các kiểu giá trị bất biến như `String`, `UUID`, số hoặc một class dữ liệu immutable khác; chỉ dùng wrapper mảng tùy chỉnh khi định danh thực sự là **nội dung byte** và có lý do rõ ràng.

## 7. Chương trình Java 17+ chạy được: `HashMap`, `HashSet`, mảng và snapshot

Tạo tệp `RecordHashKeyDemo.java` với mã dưới đây. Ví dụ coi `username` là không phân biệt chữ hoa/thường **theo hợp đồng của ví dụ**, nên chuẩn hóa trong compact constructor. Nếu hệ thống thực tế phân biệt chữ hoa/thường, phải bỏ phép chuẩn hóa đó.

```java
import java.util.*;

public class RecordHashKeyDemo {
    record AccountKey(long tenantId, String username) {
        AccountKey {
            Objects.requireNonNull(username, "username");
            username = username.strip().toLowerCase(Locale.ROOT);
            if (username.isEmpty())
                throw new IllegalArgumentException("blank username");
        }
    }

    record Location(int row, int column) {}
    record ArrayKey(byte[] data) {}
    record UnsafeTags(List<String> tags) {}

    record SafeTags(List<String> tags) {
        SafeTags { tags = List.copyOf(tags); }
    }

    public static void main(String[] args) {
        AccountKey a = new AccountKey(7, "  ALICE  ");
        AccountKey b = new AccountKey(7, "alice");
        AccountKey otherTenant = new AccountKey(8, "alice");

        System.out.println("equals=" + a.equals(b));
        System.out.println("sameHash=" + (a.hashCode() == b.hashCode()));
        System.out.println("sameReference=" + (a == b));

        Map<AccountKey, String> accounts = new HashMap<>();
        accounts.put(a, "ACTIVE");
        System.out.println("lookup=" + accounts.get(b));
        System.out.println("otherTenant=" + accounts.containsKey(otherTenant));
        accounts.put(b, "UPDATED");
        System.out.println("mapSize=" + accounts.size());
        System.out.println("newValue=" + accounts.get(a));

        Set<Location> visited = new HashSet<>();
        visited.add(new Location(2, 3));
        visited.add(new Location(2, 3));
        visited.add(new Location(3, 2));
        System.out.println("setSize=" + visited.size());

        ArrayKey first = new ArrayKey(new byte[] {1, 2});
        ArrayKey second = new ArrayKey(new byte[] {1, 2});
        System.out.println("arrayEquals=" + first.equals(second));

        List<String> source = new ArrayList<>(List.of("reader"));
        SafeTags safe = new SafeTags(source);
        UnsafeTags unsafe = new UnsafeTags(source);
        Map<SafeTags, String> safeMap = new HashMap<>();
        safeMap.put(safe, "FOUND");
        source.add("writer");
        System.out.println("safeTags=" + safe.tags());
        System.out.println("unsafeTags=" + unsafe.tags());
        System.out.println("safeLookup=" +
            safeMap.get(new SafeTags(List.of("reader"))));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp, với JDK 17 trở lên:

```bash
javac -encoding UTF-8 RecordHashKeyDemo.java
java RecordHashKeyDemo
```

**Stdout chính xác:**

```text
equals=true
sameHash=true
sameReference=false
lookup=ACTIVE
otherTenant=false
mapSize=1
newValue=UPDATED
setSize=2
arrayEquals=false
safeTags=[reader]
unsafeTags=[reader, writer]
safeLookup=FOUND
```

Giải thích đầu ra:

- `a` và `b` khác tham chiếu (`== false`) nhưng sau chuẩn hóa đều có component `(7, "alice")`, nên `equals=true` và `sameHash=true`.
- `HashMap` trả về `ACTIVE` khi tra bằng `b`. Sau khi `put(b, "UPDATED")`, entry cho khóa tương đương được cập nhật; `mapSize=1`.
- Key có `tenantId=8` không trùng key có `tenantId=7`; map không tìm thấy.
- `Set<Location>` lưu hai vị trí duy nhất `(2,3)` và `(3,2)`.
- Hai `byte[]` khác instance khiến synthesized `ArrayKey.equals` trả `false` dù nội dung trùng.
- `SafeTags` giữ snapshot `[reader]` và vẫn tra được trong map; `UnsafeTags` phản ánh `[reader, writer]` do tham chiếu tới list mutable nguồn.

## 8. Những trường hợp cần cân nhắc thêm

**`null`:** synthesized `equals()` xử lý null cho component kiểu tham chiếu thông qua ngữ nghĩa `Objects.equals`. Ví dụ hai `record Tag(String value) {}` cùng có `value = null` sẽ bằng nhau. Nhưng điều đó không biến null thành dữ liệu hợp lệ. Khi null bị cấm, kiểm tra bằng `Objects.requireNonNull` ở canonical constructor để key có bất biến rõ ràng.

**Giá trị kiểu số có ngữ nghĩa riêng:** record dùng `equals()` của component tham chiếu. Chẳng hạn hai `BigDecimal` có giá trị toán học bằng nhau nhưng khác `scale` (ví dụ `1.0` và `1.00`) không bằng nhau theo `BigDecimal.equals`; record chứa chúng cũng không bằng nhau. Nếu nghiệp vụ muốn bỏ qua scale, hãy chuẩn hóa dữ liệu một cách nhất quán ở canonical constructor và cân nhắc tình huống số không đặc biệt.

**Dấu của zero và NaN:** synthesized equality của `record Measure(double x) {}` so sánh theo `Double.compare`; vì vậy `new Measure(-0.0).equals(new Measure(+0.0))` là `false`, còn các giá trị `Double.NaN` được xem là bằng nhau. Nếu định danh nghiệp vụ khác những quy tắc đó, cần xác định và mã hóa chính sách ngay từ đầu.

**Tự override `equals()`/`hashCode()`:** Java cho phép, nhưng phải bảo đảm hai phương thức thống nhất, giữ các tính chất của `equals` (phản xạ, đối xứng, bắc cầu và nhất quán) và bất biến copy của record (`new R(r.component1(), ... )` vẫn bằng `r`). Nếu chỉ sửa `equals` mà quên `hashCode`, `HashMap`/`HashSet` có thể có hành vi sai. Khi override `toString` hoặc accessor, lưu ý synthesized equality/hash của record dựa vào field component, không dựa vào kết quả accessor tùy chỉnh.

**Đa luồng và cache:** key có component mutable vừa gây lỗi tra cứu vừa dễ sinh race condition. Tính `final` của tham chiếu record không giải quyết việc đối tượng được tham chiếu có thể bị sửa từ nơi khác. Lựa chọn an toàn là mô hình hóa key bằng giá trị bất biến và hạn chế alias có thể ghi.

**Không dùng hash code như giá trị lưu trữ bền vững:** thuật toán hash của record không được cam kết ổn định giữa các phiên bản hoặc tiến trình. Nếu cần khóa ngoài hệ thống hoặc lưu xuống cơ sở dữ liệu, hãy lưu các component định danh hoặc tạo ID ổn định riêng; nếu cần integrity/security, dùng thuật toán mật mã đúng mục tiêu.

## 9. Bảng lỗi thường gặp và cách sửa

| Lỗi thiết kế / hiện tượng | Vì sao xảy ra | Cách xử lý |
|---|---|---|
| Dùng `==` để xét hai record trùng dữ liệu | `==` so tham chiếu với đối tượng | Dùng `equals`, `Set.contains` hoặc `Map.containsKey` theo hợp đồng collection |
| Nhầm hash bằng nhau đồng nghĩa object bằng nhau | Va chạm hash là hợp lệ | Luôn để `equals()` là tiêu chí quyết định bình đẳng |
| Dùng `record Key(byte[] bytes)` và mong so sánh nội dung mảng | Array `equals` mặc định so định danh | Dùng wrapper bất biến và `Arrays.equals`/`Arrays.hashCode`, hoặc đổi mô hình dữ liệu |
| Key chứa `ArrayList` bị sửa sau `put` | Hash/equality phụ thuộc trạng thái mutable | Sao chép phòng vệ, dùng component bất biến |
| `List.copyOf` nhưng phần tử bên trong vẫn mutable | Sao chép list là nông | Sao chép/chuẩn hóa từng phần tử hoặc lưu ID bất biến |
| Override `equals()` nhưng không đồng bộ `hashCode()` | Phá hợp đồng hash | Override cả hai bằng cùng quy tắc dữ liệu |
| Dùng `TreeSet<Record>` và mong record tự sắp xếp | Record không tự có `Comparable` | Truyền `Comparator` hoặc triển khai thứ tự phù hợp |
| In hoặc lưu `record.hashCode()` làm ID | Hash có thể trùng và không có tính ổn định liên phiên | Dùng ID nghiệp vụ hoặc encoding ổn định có đặc tả |
| Muốn username không phân biệt chữ hoa nhưng tạo record từ cả hai dạng | `String.equals` phân biệt chữ hoa/thường | Chuẩn hóa có chủ đích tại điểm tạo key, dùng `Locale.ROOT` nếu thích hợp |

## 10. Checklist kiểm thử khi dùng record làm key hoặc phần tử Set

1. Tạo **hai instance khác nhau** có component tương đương: `equals()` phải `true` và hash phải bằng nhau.
2. Tạo instance có **một component định danh khác**: `equals()` phải `false` theo hợp đồng.
3. `HashMap.put(key1, value)` rồi `get(key2)` với `key2.equals(key1)`: phải tìm được giá trị; `put(key2, newValue)` chỉ thay thế entry.
4. `HashSet.add(a)`, `add(b)` với `a.equals(b)`: size chỉ tăng một lần; không phụ thuộc thứ tự duyệt.
5. Nếu component là list, mảng hoặc đối tượng mutable, thử sửa đối tượng nguồn sau khi tạo record và kiểm tra bất biến của key hoặc thiết kế phòng vệ.
6. Nếu key dùng array theo **nội dung**, test hai mảng khác instance nhưng bằng nội dung; test sửa mảng nguồn và mảng trả về từ accessor.
7. Test `null`, chuỗi rỗng, chữ hoa/thường, khoảng trắng hoặc `BigDecimal` khác scale khi các trường hợp này thuộc miền dữ liệu.
8. Không dựa vào con số `hashCode()` cụ thể: test **quan hệ** giữa equality và hash, tránh assert kết quả hash bằng một hằng số.

## Tài liệu chính thức

- Oracle, *Record Classes* (Java 17, tính năng chính thức từ Java 16): https://docs.oracle.com/en/java/javase/17/language/records.html
- Oracle JDK 26 API, `java.lang.Record` — equality, hashing, shallow immutability, contract và thuật toán hash không cố định: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Record.html
- Oracle JDK 17 API, `java.lang.Object.hashCode()` — hợp đồng hàm băm cho hash tables: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#hashCode()
- Oracle JDK 17 API, `HashMap`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html
- Oracle JDK 17 API, `HashSet`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html
- Oracle JDK 17 API, `List.copyOf`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)
