# Kiểm thử tính nhất quán của `equals`, `hashCode` và dữ liệu đầu vào với `java.util.Objects`

## 1. Bối cảnh và mục tiêu học tập

Khi một đối tượng đại diện cho **giá trị** như mã đơn hàng, khóa người dùng, tọa độ hay thông tin sản phẩm, câu hỏi “hai đối tượng có bằng nhau không?” thường không thể giải quyết chỉ bằng so sánh tham chiếu `==`. Java cung cấp hai phương thức của `Object` để định nghĩa quan hệ bằng nhau và mã băm:

- `boolean equals(Object other)`: xác định hai đối tượng có **bằng nhau theo hợp đồng của lớp** hay không.
- `int hashCode()`: cung cấp mã băm tương thích với `equals`, đặc biệt quan trọng với `HashSet`, `HashMap` và các cấu trúc băm.

Từ **Java 7**, lớp tiện ích **`java.util.Objects`** giúp diễn đạt hợp đồng rõ ràng hơn qua `Objects.equals`, `Objects.hash`, `Objects.hashCode` và `Objects.requireNonNull`. Các API này vẫn hiện hành. Bài tập trung vào **cách kiểm thử tính đúng đắn**, không chỉ cách viết các phương thức.

Một bộ kiểm thử đáng tin phải trả lời ít nhất năm câu hỏi:

1. `equals` có thỏa **phản xạ, đối xứng, bắc cầu, nhất quán và khác `null`** không?
2. Nếu hai đối tượng bằng nhau, `hashCode` của chúng có chắc chắn **bằng nhau** không?
3. `HashSet` và `HashMap` có xử lý các đối tượng bằng nhau theo giá trị đúng như dự kiến không?
4. Dữ liệu đầu vào như `null`, chuỗi rỗng, giá trị vi phạm quy tắc nghiệp vụ và giá trị hợp lệ có được xử lý theo **hợp đồng đã định nghĩa** không?
5. Những trường dùng cho `equals`/`hashCode` có giữ tính ổn định khi đối tượng nằm trong một tập hợp băm không?

**Không có một phương thức `Objects` duy nhất tự động chứng minh cả hợp đồng.** Cần thiết kế dữ liệu thử đủ đa dạng, chạy phép kiểm tra, xem các tình huống lỗi, và cập nhật test khi thay đổi cách xác định danh tính đối tượng.

## 2. Hai mức bằng nhau: tham chiếu và giá trị

`==` giữa hai biến tham chiếu kiểm tra chúng có trỏ tới **cùng đối tượng** hay không. `equals` có thể được lớp override để kiểm tra **cùng giá trị logic**:

```java
String a = new String("same");
String b = new String("same");

System.out.println(a == b);               // false
System.out.println(a.equals(b));          // true
System.out.println(Objects.equals(a, b)); // true
```

Đây là đoạn **minh họa bên trong phương thức** có `import java.util.Objects;`. Hai lần `new String` được viết có chủ đích chỉ để chứng minh sự khác biệt, không phải cách tạo chuỗi thông thường nên áp dụng trong code thực tế.

`Objects.equals(a, b)` xử lý trường hợp `null` theo cách: nếu hai tham chiếu giống nhau (bao gồm cùng `null`) thì kết quả `true`; nếu tham chiếu trái là `null` và phải không phải `null` thì `false`; còn lại nó sử dụng `a.equals(b)`.

**Khác biệt quan trọng khi viết test:**

```java
Objects.equals(null, null); // true
```

không có nghĩa `null` là một đối tượng hay `x.equals(null)` được phép trả `true`. Hợp đồng `Object.equals` quy định với đối tượng `x` khác `null`, `x.equals(null)` phải trả `false`.

Với đối tượng chưa override `equals`, implementation mặc định của `Object.equals` mang ngữ nghĩa danh tính tham chiếu. Chỉ dùng `Objects.equals` **không biến đối tượng đó thành đối tượng so sánh theo giá trị**.

## 3. Năm tính chất phải kiểm thử đối với `equals`

### 3.1. Phản xạ (*reflexive*)

Với một tham chiếu `x` khác `null`:

```java
x.equals(x) == true
```

Một test thường viết:

```java
check(a.equals(a), "reflexive");
```

Trong ví dụ này, `check` là hàm tự định nghĩa để ném `AssertionError` nếu biểu thức sai; định nghĩa đầy đủ có ở mục 9. Test phản xạ phải dùng **chính đối tượng** `a`, không thay bằng một đối tượng mới có giá trị tương đương.

### 3.2. Đối xứng (*symmetric*)

Với hai tham chiếu khác `null`, kết quả của `x.equals(y)` và `y.equals(x)` phải giống nhau:

```java
check(a.equals(b) == b.equals(a), "symmetric");
```

Đặc biệt cần kiểm thử trường hợp **một lớp cha và một lớp con** hoặc hai kiểu có quan hệ đặc biệt, vì việc dùng `instanceof` thiếu nhất quán có thể khiến `a.equals(b)` là `true` nhưng `b.equals(a)` là `false`. Dùng lớp `final` cho một value object là một cách giảm rủi ro liên quan đến kế thừa khi nghiệp vụ không cần subtype.

### 3.3. Bắc cầu (*transitive*)

Nếu `a.equals(b)` và `b.equals(c)` là `true` thì `a.equals(c)` phải là `true`:

```java
check(a.equals(b) && b.equals(c) && a.equals(c),
      "transitive");
```

Cần tạo **ít nhất ba thể hiện tương đương theo giá trị**. Một lỗi thường gặp là kết hợp quan hệ “bằng nhau gần đúng” với sai số theo từng cặp trong `equals`, khiến ba giá trị sát nhau không thỏa bắc cầu. Nếu cần so sánh số gần đúng để tính toán, thường nên dùng hàm so sánh riêng thay vì biến `equals` của khóa băm thành phép so sánh phụ thuộc khoảng cách.

### 3.4. Nhất quán (*consistent*)

Nhiều lần gọi `x.equals(y)` với cùng trạng thái dữ liệu liên quan phải cho cùng kết quả. Test tối thiểu là gọi nhiều lần:

```java
for (int i = 0; i < 3; i++) {
    check(a.equals(b), "consistent");
}
```

Điều kiện ngầm: **không thay đổi các trường tham gia so sánh** trong thời gian thử. `equals` không nên phụ thuộc đồng hồ, số ngẫu nhiên, bộ đếm lời gọi hay dữ liệu môi trường thay đổi không được phản ánh trong hợp đồng.

Lặp lại ba lần chỉ là phép kiểm tra mẫu; **nó không chứng minh tính nhất quán cho mọi đường chạy**. Kết hợp test tình huống, review implementation và kiểm thử dựa trên thuộc tính (*property-based testing*) khi hệ thống có hạ tầng phù hợp.

### 3.5. Khác `null`

Với `a != null`:

```java
check(!a.equals(null), "not equal to null");
```

Cũng nên có test **khác kiểu không liên quan**:

```java
check(!a.equals("A-1"), "not equal to other type");
```

Không viết `equals` sao cho nó ném `ClassCastException` khi gặp kiểu lạ; implementation thông thường nên kiểm tra kiểu và trả `false`. Dù `Objects.equals` giúp tránh việc gọi phương thức trên tham chiếu `null`, test này vẫn cần thiết cho **phần override của lớp**.

## 4. Hợp đồng `hashCode`: kiểm thử điều bắt buộc và điều không bắt buộc

Hợp đồng trọng tâm:

> Nếu `a.equals(b)` trả `true` thì `a.hashCode() == b.hashCode()` **bắt buộc** trả `true`.

Một test thích hợp:

```java
check(a.equals(b), "equal values");
check(a.hashCode() == b.hashCode(), "equal objects same hash");
```

Hai đối tượng khác nhau theo `equals` **được phép** có cùng `hashCode`. Vì vậy test sau là **sai về mặt yêu cầu hợp đồng**:

```java
// Sai kỳ vọng: Java KHÔNG bắt buộc hash phải khác nhau.
// check(!a.equals(different)
//       && a.hashCode() != different.hashCode(), "different hashes");
```

Hash code là một số `int` hữu hạn; nhiều giá trị khác nhau có thể cùng mã băm (*collision*). Một thuật toán băm tốt mong muốn phân phối tương đối đều, nhưng hợp đồng Java **không bảo đảm không va chạm**.

Ngoài ra, `hashCode` phải nhất quán qua nhiều lần gọi **khi dữ liệu liên quan không thay đổi**. Test có thể kiểm tra:

```java
int initialHash = a.hashCode();
check(initialHash == a.hashCode(), "stable hash");
```

### `Objects.hash` và `Objects.hashCode` không đồng nghĩa

- `Objects.hashCode(value)`: nếu `value` là `null`, trả `0`; nếu khác `null`, dùng `value.hashCode()`.
- `Objects.hash(field1, field2, ...)`: tạo mã băm tổng hợp từ các giá trị, thường hữu ích cho việc override `hashCode` của value object.

```java
@Override
public int hashCode() {
    return Objects.hash(id, region);
}
```

**Điều kiện quan trọng:** các trường mà `equals` sử dụng phải được phản ánh **nhất quán** trong mã băm. `hashCode` **không nhất thiết** phải sử dụng mọi trường của `equals` (dùng ít trường hơn có thể tăng va chạm nhưng vẫn đúng nếu không vi phạm quy tắc), song tuyệt đối không được dựa vào một trường có thể khác nhau giữa các đối tượng mà `equals` lại xem là bằng nhau.

Với trường là mảng, không mặc định `Objects.hashCode(array)` sẽ băm theo nội dung mảng; cần `Arrays.hashCode` hoặc `Arrays.deepHashCode` tương ứng nếu `equals` so sánh nội dung mảng.

## 5. Thiết kế một value object đơn giản để kiểm thử

Giả sử `AccountKey` định danh một tài khoản bằng hai thành phần:

- `id`: bắt buộc có giá trị, không được `null` và không được toàn dấu cách.
- `region`: có thể `null` theo hợp đồng nghiệp vụ.
- Hai `AccountKey` bằng nhau **chỉ khi cả `id` và `region` cùng bằng nhau**.
- Khi hai khóa bằng nhau, mã băm phải bằng nhau.
- Sau khi tạo, các trường tham gia so sánh **không bị gán lại**.

Thiết kế phù hợp:

```java
private static final class AccountKey {
    private final String id;
    private final String region;

    private AccountKey(String id, String region) {
        this.id = Objects.requireNonNull(id, "id");
        if (id.isBlank()) {
            throw new IllegalArgumentException("id must not be blank");
        }
        this.region = region;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof AccountKey key)) return false;
        return id.equals(key.id)
                && Objects.equals(region, key.region);
    }

    @Override
    public int hashCode() {
        return Objects.hash(id, region);
    }
}
```

Đoạn trên là **lớp lồng bên trong một lớp ngoài**; nó không phải một tệp độc lập. Chương trình hoàn chỉnh ở mục 9.

Phân tích:

1. `Objects.requireNonNull(id,"id")` từ Java 7 từ chối `null` ngay tại constructor.
2. `String.isBlank()` có từ **Java 11** và dùng được trên baseline **Java 17+**; nó từ chối chuỗi chỉ có ký tự khoảng trắng theo quy tắc của `isBlank`. Nếu ứng dụng còn chạy JDK cũ, cần validation tương thích phiên bản tương ứng.
3. `region` cho phép `null` nên phải dùng `Objects.equals(region,key.region)` hoặc cách kiểm tra tương đương.
4. Cú pháp `instanceof AccountKey key` là **pattern matching** chính thức ở Java 16+, nên ví dụ chạy trên Java 17+. Quy tắc cơ bản của `equals`/`hashCode` đã có từ lâu và vẫn đúng.
5. Lớp `final` không cho kế thừa, tránh một nhóm vấn đề đối xứng do override `equals` giữa các subtype.
6. Hai trường đều là `String` bất biến và tham chiếu `final`, vì vậy giá trị tham gia so sánh không đổi sau khi xây dựng.
7. `hashCode` dùng đúng hai thành phần `equals` so sánh.

**Vì sao cần quy định trước hợp đồng dữ liệu đầu vào?** Nếu nghiệp vụ muốn `id` không phân biệt hoa/thường, hoặc `region` phải thuộc tập mã hợp lệ, ta phải xác định việc chuẩn hóa/validation **trước khi** tạo khóa và viết test tương ứng. Không tự suy ra rằng mọi `String` nên dùng `trim`/`toLowerCase` hay mọi `null` đều không hợp lệ.

## 6. Kiểm thử dữ liệu đầu vào: đúng loại lỗi, đúng thời điểm

### 6.1. Test `null` cho trường bắt buộc

Với `id` bắt buộc khác `null`:

```java
expectFailure(NullPointerException.class,
        () -> new AccountKey(null, "VN"),
        "null id");
```

`expectFailure` là helper kiểm thử được định nghĩa trong chương trình ở mục 9. `Objects.requireNonNull(id,"id")` giúp phát hiện lỗi ngay ở constructor, thay vì tạo đối tượng ở trạng thái không hợp lệ và chỉ lỗi khi gọi `hashCode`/`equals` sau này.

**Không phải mọi `null` đều sai.** Với trường `region` được phép `null`, test phù hợp lại là:

```java
AccountKey a = new AccountKey("B-2", null);
AccountKey b = new AccountKey("B-2", null);
check(Objects.equals(a, b), "nullable region");
```

Test cả trường hợp một phía `null` và một phía có giá trị để xác nhận quan hệ bằng nhau diễn đạt đúng hợp đồng.

### 6.2. Test dữ liệu rỗng hoặc toàn khoảng trắng

Nếu `id` không được để trống:

```java
expectFailure(IllegalArgumentException.class,
        () -> new AccountKey("  ", "VN"),
        "blank id");
```

Tại đây `NullPointerException` biểu đạt vi phạm điều kiện không `null`, còn `IllegalArgumentException` biểu đạt tham số có mặt nhưng **không đáp ứng quy tắc nghiệp vụ**. Hai loại lỗi có mục đích khác nhau. Đừng dùng `Objects.requireNonNull` để thay thế mọi loại validation.

Tùy nhu cầu, cần thêm test cho `""`, `"  "`, giá trị có tab/xuống dòng, chuỗi dài bất thường, ký tự Unicode, dữ liệu sai chuẩn và trường hợp hợp lệ ở biên. Không mặc định các giới hạn này nếu API chưa hề đặt ra.

### 6.3. Giá trị dự phòng và rủi ro che dữ liệu lỗi

`Objects.requireNonNullElse(value,fallback)` được bổ sung ở **Java 9**:

```java
String name = Objects.requireNonNullElse(null, "guest");
```

Đây là cách chọn một giá trị **khác `null`** khi hợp đồng cho phép default. Nhưng **không nên tự dùng giá trị mặc định cho định danh bắt buộc**: thay mọi `id == null` thành `"unknown"` có thể khiến những đối tượng không có định danh bị coi là **bằng nhau** và xuất hiện trùng trong `HashSet` hoặc bị ghi đè trong `HashMap`.

`Objects.requireNonNullElseGet(value,supplier)` (Java 9+) dùng khi giá trị mặc định cần tính **chỉ lúc giá trị đầu vào là `null`**. Với dữ liệu có thể `null` theo thiết kế, cũng có thể giữ `null` và xử lý qua `Objects.equals`; không bắt buộc biến mọi null thành chuỗi giả.

### 6.4. Xác thực không nhất thiết thuộc `equals`

Đặt validation quan trọng ở **constructor, factory hoặc ranh giới API**, thay vì chờ `equals` tự phát hiện trạng thái không hợp lệ. `equals` nên là phép kiểm tra quan hệ bằng nhau, không phải quy trình chuẩn hóa dữ liệu tạo side effect.

Một mẫu chuẩn hóa có chủ đích:

```java
// Minh họa đặt trong constructor khi hợp đồng quy định ID
// không phân biệt chữ hoa/thường theo quy tắc độc lập locale.
String normalized = Objects.requireNonNull(id, "id")
        .toLowerCase(java.util.Locale.ROOT);
```

Nếu áp dụng chuẩn hóa, cần test `"ABC"` và `"abc"` được xử lý đúng **cả `equals` lẫn `hashCode`**. Đồng thời, không dùng phép chuẩn hóa này cho mã phân biệt hoa/thường; business contract quyết định.

## 7. Kiểm thử hành vi thực tế với `HashSet` và `HashMap`

Các phép kiểm tra trực tiếp `equals` và `hashCode` chưa đủ để phát hiện mọi vấn đề tích hợp. Cần test một chuỗi sử dụng thực tế:

```java
AccountKey a = new AccountKey("A-1", "VN");
AccountKey b = new AccountKey("A-1", "VN");

Set<AccountKey> unique = new HashSet<>();
unique.add(a);
unique.add(b);

check(unique.size() == 1, "set deduplicates");

Map<AccountKey, Integer> index = new HashMap<>();
index.put(a, 42);

check(Objects.equals(index.get(b), 42), "map lookup");
```

Các câu lệnh trên đặt trong lớp kiểm thử của mục 9 với `import` tương ứng. Nếu `a.equals(b)` đúng và hash tương thích, `HashSet` không lưu hai phần tử tách biệt theo quan hệ bằng nhau; `HashMap` có thể tìm giá trị bằng **một khóa mới nhưng bằng nhau theo giá trị**.

Tại sao test này hữu ích?

- Nó kiểm tra trực tiếp cách hợp đồng được dùng trong thực tế.
- Nó phát hiện lớp quên override `hashCode` trong khi đã override `equals` (test cụ thể không bảo đảm phơi bày mọi lỗi nhưng rất có ích).
- Nó cho thấy hai khóa khác tham chiếu có thể được dùng thay thế nhau khi hợp đồng cho phép.

**Không nên** test `new HashSet<>(...)` rồi bắt buộc thứ tự phần tử giống thứ tự thêm. `HashSet` không có cam kết thứ tự lặp. Cũng không nên đòi hai khóa khác nhau phải có mã băm khác nhau.

### Trường hợp khóa thay đổi trạng thái

Ví dụ **cố ý mang nguy cơ**:

```java
// Mã minh họa, các lớp/phương thức phụ trợ phải do ứng dụng định nghĩa.
MutableKey key = new MutableKey("A");
Map<MutableKey, Integer> map = new HashMap<>();

map.put(key, 1);
key.setId("B"); // Thay đổi dữ liệu được dùng trong equals/hashCode.
// map.get(key) có thể không tìm thấy giá trị như mong đợi.
```

Nếu mã băm của khóa thay đổi sau `put`, khóa có thể còn nằm trong vị trí được tính theo mã băm cũ. Khi đó `get`, `containsKey` hoặc `remove` có thể không hoạt động như mong muốn. Ví dụ không đưa ra stdout cố định vì hành vi phụ thuộc cách triển khai `MutableKey` và mã băm cụ thể.

**Thực hành tốt:** đối với khóa dùng trong cấu trúc băm, ưu tiên đối tượng mang giá trị **bất biến**. Nếu bắt buộc cho phép sửa nội dung, không thay đổi các trường tham gia `equals`/`hashCode` khi đối tượng đang làm khóa; hoặc tạo khóa mới và cập nhật map/set một cách có chủ đích.

## 8. Những lỗi hợp đồng nên thử bằng test âm

### 8.1. Override `equals` nhưng không override `hashCode`

```java
final class BadKey {
    private final String id;

    BadKey(String id) {
        this.id = id;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof BadKey b
                && Objects.equals(id, b.id);
    }

    // Cố ý KHÔNG override hashCode().
}
```

Đây là lớp **cố ý sai** về hợp đồng `equals`/`hashCode` khi có hai thể hiện bằng nhau theo giá trị nhưng khác danh tính. `Object.hashCode()` mặc định không được cam kết tương thích với quan hệ bằng nhau mới của `BadKey`. Không nên dựa vào khả năng tình cờ hai hash code giống nhau để coi class đúng.

**Sửa:** override `hashCode` dựa vào `id`:

```java
@Override
public int hashCode() {
    return Objects.hashCode(id);
}
```

Đây là **phương thức sửa lỗi** cần thêm vào lớp `BadKey`. Khi `id` có thể là `null`, `Objects.hashCode(id)` trả `0` thay vì ném lỗi.

### 8.2. Dùng bộ trường khác nhau theo chiều nguy hiểm

Giả sử `equals` so sánh **chỉ `id`**, nhưng `hashCode` băm `id` và `region`:

```java
// Sai về nguyên tắc nếu equals chỉ xét id.
@Override
public int hashCode() {
    return Objects.hash(id, region);
}
```

Hai đối tượng có cùng `id` nhưng `region` khác nhau có thể được `equals` coi bằng nhau; mã băm của chúng lại có thể khác nhau. Đây là vi phạm trực tiếp. Một test phải tạo **hai đối tượng bằng nhau theo định nghĩa** nhưng với trường không thuộc `equals` khác nhau, rồi so sánh mã băm.

Ngược lại, nếu `equals` so sánh cả hai trường mà `hashCode` chỉ băm `id`, điều đó **chưa chắc** vi phạm: hai đối tượng bằng nhau vẫn có cùng `id` và cùng hash. Tuy vậy có thể gây nhiều va chạm hơn. Bài test không nên áp đặt quy tắc sai rằng hash phải liệt kê **chính xác mọi trường của `equals`**; quy tắc bắt buộc là **hai đối tượng bằng nhau phải cùng hash**.

### 8.3. Sai đối xứng do kế thừa

Một lớp cha coi hai đối tượng bằng nhau khi cùng `id`, nhưng lớp con đòi so thêm `department` có thể làm kết quả `parent.equals(child)` và `child.equals(parent)` khác nhau. Bài test phải thử **cả hai chiều**, không chỉ gọi một lần.

Khi lớp đại diện giá trị mà không cần kế thừa, khai báo `final` là cách giảm một nhóm rủi ro. Nếu cần kế thừa, hãy thiết kế quan hệ `equals` nghiêm túc và test trên **mọi loại đối tượng tương tác**.

### 8.4. So sánh mảng bằng tham chiếu khi muốn theo nội dung

`Objects.equals(arrayA,arrayB)` đối với hai mảng khác nhau vẫn dựa trên `Object.equals` của mảng và thường là `false`, dù các phần tử giống nhau:

```java
int[] a = {1, 2};
int[] b = {1, 2};

boolean shallow = Objects.equals(a, b);     // false
boolean deep = Objects.deepEquals(a, b);    // true
```

Nếu một value object chứa mảng và muốn so sánh **nội dung**, hãy kết hợp:

```java
java.util.Arrays.equals(data, other.data)
java.util.Arrays.hashCode(data)
```

Hai biểu thức này minh họa so sánh và băm cùng **nội dung mảng một chiều**. Với mảng đối tượng lồng nhau có thể dùng `Arrays.deepEquals` và `Arrays.deepHashCode` phù hợp. `Objects.deepEquals` là tiện ích hữu ích để so sánh hai đối tượng có thể là mảng, nhưng **không thể suy ra rằng `Objects.hash(array)` luôn băm sâu đúng theo `deepEquals`**.

## 9. Chương trình Java 17+ hoàn chỉnh: 18 phép kiểm tra hợp đồng

Chương trình dưới đây tự chứa cả lớp đang kiểm thử, helper `check` và helper `expectFailure`. Nó không cần thư viện test ngoài. Khi một điều kiện thất bại, chương trình ném `AssertionError` và kết thúc với lỗi, thay vì chỉ in thông điệp “failed” rồi tiếp tục.

Tạo tệp **`ObjectContractTests.java`**:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class ObjectContractTests {
    private static int checks;

    private static final class AccountKey {
        private final String id;
        private final String region;

        private AccountKey(String id, String region) {
            this.id = Objects.requireNonNull(id, "id");
            if (id.isBlank()) {
                throw new IllegalArgumentException("id must not be blank");
            }
            this.region = region; // region may be null by design.
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof AccountKey key)) return false;
            return id.equals(key.id)
                    && Objects.equals(region, key.region);
        }

        @Override
        public int hashCode() {
            return Objects.hash(id, region);
        }

        @Override
        public String toString() {
            return "AccountKey[id=" + id + ", region="
                    + Objects.toString(region, "(none)") + "]";
        }
    }

    private static void check(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
        checks++;
    }

    private static void expectFailure(Class<? extends Throwable> type,
                                      Runnable action, String label) {
        try {
            action.run();
        } catch (Throwable failure) {
            if (type.isInstance(failure)) {
                checks++;
                return;
            }
            throw new AssertionError(label + ": wrong exception", failure);
        }
        throw new AssertionError(label + ": no exception");
    }

    public static void main(String[] args) {
        AccountKey a = new AccountKey("A-1", "VN");
        AccountKey b = new AccountKey("A-1", "VN");
        AccountKey c = new AccountKey("A-1", "VN");
        AccountKey different = new AccountKey("A-1", "SG");

        check(a.equals(a), "reflexive");
        check(a.equals(b) && b.equals(a), "symmetric");
        check(a.equals(b) && b.equals(c) && a.equals(c), "transitive");
        for (int i = 0; i < 3; i++) {
            check(a.equals(b), "consistent");
        }
        check(!a.equals(null), "not equal to null");
        check(!a.equals("A-1"), "not equal to other type");
        check(!a.equals(different), "distinct values");
        System.out.println("equals contract: PASS");

        check(a.hashCode() == b.hashCode(), "equal objects same hash");
        check(a.hashCode() == a.hashCode(), "stable hash");
        Set<AccountKey> unique = new HashSet<>();
        unique.add(a);
        unique.add(b);
        check(unique.size() == 1, "set deduplicates");
        Map<AccountKey, Integer> index = new HashMap<>();
        index.put(a, 42);
        check(Objects.equals(index.get(b), 42), "map lookup");
        System.out.println("hash collections: PASS");

        check(Objects.equals(
                new AccountKey("B-2", null),
                new AccountKey("B-2", null)), "nullable region");
        check(!Objects.equals(
                new AccountKey("B-2", null),
                new AccountKey("B-2", "VN")), "null vs value");
        expectFailure(NullPointerException.class,
                () -> new AccountKey(null, "VN"), "null id");
        expectFailure(IllegalArgumentException.class,
                () -> new AccountKey("  ", "VN"), "blank id");
        check(Objects.requireNonNullElse(null, "guest").equals("guest"),
                "default value");
        System.out.println("input validation: PASS");

        System.out.println("sample = " + a);
        System.out.println("checks = " + checks);
    }
}
```

Biên dịch với JDK 17 trở lên; `--release 17` giúp xác nhận mã không phụ thuộc API/cú pháp mới hơn Java 17:

```bash
javac --release 17 -Xlint:all -Werror -encoding UTF-8 ObjectContractTests.java
java ObjectContractTests
```

**Stdout chính xác:**

```text
equals contract: PASS
hash collections: PASS
input validation: PASS
sample = AccountKey[id=A-1, region=VN]
checks = 18
```

Ý nghĩa kết quả:

- Nhóm `equals contract` kiểm tra các tính chất quan trọng trên những thể hiện có giá trị tương đương, đối tượng khác giá trị, `null` và kiểu không liên quan.
- Nhóm `hash collections` kiểm tra mã băm phù hợp và hành vi có ý nghĩa trong `HashSet`/`HashMap`; không phụ thuộc thứ tự lặp của tập hợp.
- Nhóm `input validation` kiểm tra trường cho phép `null`, trường bắt buộc khác `null` và ID không được toàn dấu cách. `expectFailure` chỉ tăng số test nếu lỗi thuộc loại mong đợi.
- `toString` của đối tượng in giá trị rõ ràng; ở đây nó được override riêng. Không phải mọi lớp Java sẽ tự có biểu diễn chuỗi như vậy.
- Toàn bộ **18 phép kiểm tra** đạt; nếu bất kỳ kiểm tra nào thất bại, chương trình ném `AssertionError`, không in đầy đủ kết quả PASS ở cuối.

**Giới hạn của bộ test:** Một bộ dữ liệu hữu hạn không thể chứng minh mọi tính chất cho mọi trạng thái có thể có. Nó là **bộ kiểm thử minh họa độc lập**, phù hợp cho học và chạy nhanh; hệ thống thực tế nên kết hợp unit test chuyên dụng, test sinh dữ liệu và review hợp đồng.

## 10. Tổ chức test theo bảng dữ liệu thay vì viết riêng từng trường hợp

Với nhiều trường `id` và `region`, nên xây dựng **bảng ca kiểm thử**:

| Dữ liệu 1 | Dữ liệu 2 | Mong đợi `equals` | Cần kiểm tra thêm |
| --- | --- | --- | --- |
| `("A","VN")` | `("A","VN")` | `true` | Hai mã băm phải bằng |
| `("A","VN")` | `("A","SG")` | `false` | Không đòi hai mã băm khác nhau |
| `("A",null)` | `("A",null)` | `true` | `hashCode` không ném lỗi |
| `("A",null)` | `("A","VN")` | `false` | So sánh được cả hai chiều |
| `("A","VN")` | `("B","VN")` | `false` | Không phụ thuộc tham chiếu |
| Cùng đối tượng | Chính nó | `true` | Phản xạ |
| Một `AccountKey` | `null` | `false` khi gọi `key.equals(null)` | Không ném `NullPointerException` |
| Một `AccountKey` | Một `String` | `false` | Không ném `ClassCastException` |

Tổ chức theo bảng giúp phát hiện các trường hợp bị bỏ quên khi thêm trường mới. Nếu nghiệp vụ cho phép chuẩn hóa mã vùng, thêm ca chữ hoa/chữ thường, mã alias hoặc giá trị Unicode theo đúng quy tắc; đừng tự phát minh quy tắc trước khi hiểu mô hình dữ liệu.

Đối với một lớp có nhiều trường, nên có ít nhất một test mà **chỉ một trường tham gia `equals` khác nhau**, để bảo đảm trường đó thực sự được xem xét. Nếu `equals` bỏ quên `region` nhưng `hashCode` vẫn dùng `region`, các ca hai region khác nhau sẽ giúp phát hiện thiếu nhất quán.

## 11. Các hướng kiểm thử nâng cao còn có giá trị hiện nay

### 11.1. Property-based testing

Thay vì chỉ dùng vài giá trị cố định, bộ test có thể **sinh nhiều đối tượng** và kiểm tra các bất biến:

```text
Với mọi x:
    x.equals(x) == true

Với mọi x, y:
    x.equals(y) == y.equals(x)

Với mọi x, y, z:
    nếu x.equals(y) và y.equals(z)
    thì x.equals(z)

Với mọi x, y:
    nếu x.equals(y)
    thì x.hashCode() == y.hashCode()
```

Đây là **đặc tả kiểm thử dạng mã giả**, không phải cú pháp Java thực thi. Property-based testing hữu ích để sinh các tổ hợp `null`, chuỗi Unicode, dữ liệu ở biên và nhiều đối tượng khác nhau. Cần generator **tuân thủ hợp đồng dữ liệu hợp lệ** và cả generator cho input sai để test validation. Chú ý tạo mẫu có **nhiều cặp bằng nhau**; nếu toàn bộ giá trị sinh ra đều khác nhau, phép kéo theo liên quan đến hai đối tượng bằng nhau có thể qua test mà không kiểm tra được tình huống quan trọng.

### 11.2. Mutation testing

Một cách đánh giá sức mạnh test là **cố ý thay đổi implementation** trong môi trường kiểm thử:

- Bỏ trường `region` khỏi `equals`.
- Thay `Objects.equals(region,other.region)` bằng `region.equals(other.region)` để xem test `null` có bắt được lỗi không.
- Đổi bộ trường của `hashCode`.
- Bỏ một ràng buộc dữ liệu đầu vào.
- Làm `equals` trả kết quả khác khi số lần gọi tăng.

Bộ test có giá trị khi các thay đổi vi phạm hợp đồng khiến kiểm thử **thất bại**. Mutation testing không thay thế việc phân tích hợp đồng; nó giúp kiểm tra rằng bộ test thực sự có khả năng phát hiện lỗi, thay vì chỉ đi qua vài nhánh dễ.

### 11.3. Dùng JUnit hoặc hệ thống unit test của dự án

Chương trình mục 9 sử dụng `AssertionError` để không cần thư viện ngoài. Trong dự án, có thể chuyển mỗi nhóm thành test riêng trong framework hiện có. Các thao tác tương ứng thường là:

```java
// Minh họa cú pháp JUnit Jupiter, cần dependency test phù hợp.
org.junit.jupiter.api.Assertions.assertEquals(a, b);
org.junit.jupiter.api.Assertions.assertEquals(
        a.hashCode(), b.hashCode());
org.junit.jupiter.api.Assertions.assertThrows(
        NullPointerException.class,
        () -> new AccountKey(null, "VN"));
```

Đây là **đoạn minh họa phụ thuộc thư viện test ngoài**, không chạy độc lập chỉ với JDK. `AccountKey` cần xuất hiện trong phạm vi test và có constructor phù hợp. Thực tế nên gom ca kiểm thử bằng test parameterized nếu dự án có hỗ trợ, nhưng không cần thêm một framework chỉ để làm ba phép kiểm tra đơn giản.

### 11.4. Kiểm thử hợp đồng sau khi refactor

Khi thay đổi `equals` hoặc thêm trường mới, hãy xem lại toàn bộ:

1. Dữ liệu nào định nghĩa danh tính?
2. Mã băm có còn tương thích?
3. Khóa trong `HashMap`/`HashSet` có giữ trạng thái bất biến?
4. Các ca input `null`/rỗng có đổi?
5. Đối tượng cũ và mới trong hệ thống có kỳ vọng tương đương không?
6. Có thêm subtype, serialization hay dữ liệu chuyển đổi nào ảnh hưởng hợp đồng?

Test nên diễn đạt **hành vi mong đợi của nghiệp vụ**, không chỉ chụp một giá trị hash cố định từ phiên bản hiện tại rồi coi đó là API bắt buộc vĩnh viễn.

## 12. `record` có giúp giảm lỗi không?

Với Java 16+, một `record` có thể tự sinh `equals`, `hashCode` và `toString` từ các record components:

```java
record AccountKeyRecord(String id, String region) {
    AccountKeyRecord {
        Objects.requireNonNull(id, "id");
        if (id.isBlank()) {
            throw new IllegalArgumentException("id must not be blank");
        }
    }
}
```

Đây là **ví dụ Java 17+** (cần `import java.util.Objects;`) và phù hợp khi đối tượng chủ yếu lưu giá trị. Tuy nhiên:

- `record` không tự hiểu quy tắc nghiệp vụ: phải tự kiểm tra `id` và xác định `region` có thể `null` hay không.
- `record` ngầm định các trường thành phần là `final` về tham chiếu, nhưng nếu component là **một list hoặc mảng mutable**, object vẫn có thể bị thay đổi gián tiếp.
- Đặc biệt, với component là **mảng**, `equals` và `hashCode` được sinh theo hợp đồng của component, thường dựa trên tham chiếu của mảng, **không tự so sánh sâu nội dung mảng**. Muốn semantics theo nội dung, cần mô hình lại hoặc triển khai có chủ đích và test cả hai phương thức.

Vì vậy, record thường giảm lượng mã lặp và sai sót cơ bản, nhưng vẫn phải chạy test hợp đồng và test dữ liệu đầu vào. Nếu dự án dùng Java 7/8, record chưa có; không lấy cú pháp record làm ví dụ biên dịch cho những baseline đó.

## 13. Bảo vệ tính bất biến: đừng chỉ nhìn thấy `final`

Trường `final` ngăn **gán lại tham chiếu**, nhưng không ngăn đối tượng được trỏ tới bị sửa. Ví dụ:

```java
final class TagKey {
    private final java.util.List<String> tags;

    TagKey(java.util.List<String> tags) {
        this.tags = java.util.List.copyOf(
                Objects.requireNonNull(tags, "tags"));
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof TagKey k
                && tags.equals(k.tags);
    }

    @Override
    public int hashCode() {
        return tags.hashCode();
    }
}
```

Đây là **lớp minh họa Java 17+** với `import java.util.Objects;`. `List.copyOf` (Java 10+) tạo collection không cho phép sửa cấu trúc thông qua tham chiếu trả về và giữ một bản sao thích hợp theo hợp đồng. Đối với `String` bất biến, cách này giảm nguy cơ caller sửa list gốc khiến hash của khóa thay đổi. `List.copyOf` **không deep-copy những phần tử mutable** trong một list tổng quát; ví dụ này dùng `List<String>` nên phần tử cũng bất biến.

Nếu hợp đồng cho phép phần tử `null` trong list, cần chọn chiến lược khác: `List.copyOf` không chấp nhận phần tử `null`. Đừng dùng nó mà không kiểm tra quy định dữ liệu.

Trường kiểu `int[]` cần được **clone/sao chép phòng vệ** khi nhận đầu vào nếu không muốn caller sửa mảng sau khi đưa vào khóa. Khi getter trả lại mảng, cũng phải cân nhắc sao chép đầu ra. Dữ liệu tham gia `equals`/`hashCode` cần một chính sách vòng đời rõ ràng.

## 14. Những sai lầm khi kiểm thử

| Sai lầm | Hệ quả | Kiểm thử đúng hơn |
| --- | --- | --- |
| Chỉ test `a.equals(a)` | Không phát hiện sai đối xứng, bắc cầu, null | Dùng ít nhất hai, ba thể hiện và dữ liệu khác loại |
| Chỉ test một chiều `a.equals(b)` | Có thể bỏ sót khác biệt do subclass | Test cả `a.equals(b)` và `b.equals(a)` |
| Bỏ qua `hashCode` vì `equals` đã đúng | `HashSet`/`HashMap` có thể sai | So sánh hash của các cặp bằng nhau và test collections |
| Ép hai đối tượng không bằng nhau phải có hash khác nhau | Tạo yêu cầu Java không hề bảo đảm | Chấp nhận hash collision |
| Cố so khớp chính xác một số hash cụ thể trong mọi JDK | Có thể ràng buộc test vào chi tiết không cần thiết | Kiểm tra bất biến, không đoán hash |
| Dùng `==` để test value object | Chỉ kiểm tra danh tính tham chiếu | Dùng `equals`/`Objects.equals` |
| Gọi `Objects.equals` và cho rằng không cần test class override | Không tự sửa implementation sai | Test hợp đồng của lớp |
| Bỏ dữ liệu `null` vì “không bao giờ có” | Rủi ro nhập liệu, tích hợp hoặc thay đổi API | Test input hợp lệ và không hợp lệ theo hợp đồng |
| Chỉ kiểm tra exception nào đó, không kiểm tra loại | Có thể bỏ lọt lỗi ném sai kiểu | Dùng test kỳ vọng loại exception chính xác |
| Bỏ kiểm tra chuỗi rỗng hoặc toàn dấu cách | Đối tượng được tạo ở trạng thái sai | Test giá trị biên và validation |
| Thay `null` ID bằng default chung không có chủ đích | Nhiều khóa khác nhau có thể bị đồng nhất | Từ chối null khi ID bắt buộc |
| Dùng đối tượng mutable làm hash key rồi sửa | Không thể tìm lại khóa đúng | Ưu tiên khóa bất biến, test không thay đổi |
| Chỉ test hash trực tiếp, không thử `HashMap`/`HashSet` | Bỏ sót lỗi tích hợp | Thử thêm, tra cứu và khử trùng lặp |
| Tin rằng `record` tự kiểm tra mọi dữ liệu | Record vẫn có thể chứa giá trị không hợp lệ | Thêm constructor validation và test |
| Nghĩ `final List` là deep immutable | Caller có thể sửa list hoặc phần tử nếu không sao chép | Defensive copy theo hợp đồng |
| Dùng bản chạy đơn lẻ để tuyên bố chứng minh tuyệt đối | Không bao phủ mọi đường đi | Kết hợp review, test nhiều ca, property-based |

## 15. Bài tập tự luyện và đáp án

### Bài 1 — Phân biệt số hash và tính bằng nhau

Hai đối tượng `a` và `b` **không bằng nhau theo `equals`** nhưng cùng `hashCode`. Có vi phạm hợp đồng không?

**Đáp án:** Không. Va chạm mã băm là hợp lệ. Điều bắt buộc là **nếu `equals` là `true` thì hash phải bằng nhau**, không có yêu cầu đảo chiều.

### Bài 2 — Đánh giá một implementation sai

```java
final class User {
    String id;
    String group;

    @Override
    public boolean equals(Object other) {
        return other instanceof User u
                && Objects.equals(id, u.id);
    }

    @Override
    public int hashCode() {
        return Objects.hash(id, group);
    }
}
```

**Câu hỏi:** Hai `User` cùng `id` nhưng khác `group` tạo nguy cơ gì?

**Đáp án:** `equals` cho rằng bằng nhau vì chỉ xét `id`, nhưng `hashCode` lại xét thêm `group` có thể khác nhau. Khi các mã băm khác, hợp đồng bị vi phạm. Sửa `hashCode` chỉ dựa trên `id` hoặc đổi `equals` để xét `group` theo nghiệp vụ, rồi test hai trường hợp.

### Bài 3 — Kiểm tra tính đối xứng

Một lớp cha coi hai đối tượng cùng `id` là bằng nhau; lớp con so thêm một trường. Cần thử phép kiểm tra nào?

**Đáp án:** Tạo một đối tượng lớp cha và một đối tượng lớp con có dữ liệu liên quan, kiểm tra cả `parent.equals(child)` và `child.equals(parent)`; kết quả phải giống nhau. Nếu không thể giữ hợp đồng khi kế thừa, cân nhắc tách value type hoặc dùng lớp `final`.

### Bài 4 — Input `null` cho khóa bắt buộc

Constructor nhận `id` là `null` nhưng gán default `"unknown"` trước khi tạo khóa. Tại sao cần cẩn trọng?

**Đáp án:** Mọi đầu vào thiếu `id` có thể biến thành cùng khóa `"unknown"`, dẫn đến bị khử trùng lặp hoặc ghi đè dữ liệu trong hash collections. Nếu `id` bắt buộc, phù hợp hơn là từ chối input bằng `Objects.requireNonNull` và test đúng loại exception.

### Bài 5 — Một mảng tham gia hợp đồng

`int[] a = {1,2}; int[] b = {1,2};`. Khi muốn hai mảng này bằng nhau theo nội dung, nên dùng gì trong `equals` và `hashCode`?

**Đáp án:** Dùng `Arrays.equals(a,b)` và `Arrays.hashCode(a)`; không dùng hash dựa trên danh tính của chính mảng. Nếu mảng có thể bị caller sửa, hãy sao chép phòng vệ để hash không đổi khi đối tượng được dùng làm khóa.

### Bài 6 — Vì sao cần test `HashMap`?

Hai `AccountKey` khác tham chiếu có cùng `id` và `region`. Sau khi `map.put(a,42)`, `map.get(b)` nên làm gì?

**Đáp án:** Nếu `a.equals(b)` là `true` và `hashCode` tương thích, `map.get(b)` phải tìm được `42`. Test này kiểm tra ứng dụng thực tế của hợp đồng, không chỉ so sánh một con số hash.

### Bài 7 — Test property-based có đủ khi dữ liệu sinh luôn khác nhau?

Nếu generator sinh hàng nghìn khóa nhưng **không có bất kỳ cặp nào bằng nhau**, test `a.equals(b) ⇒ a.hashCode()==b.hashCode()` có đáng tin không?

**Đáp án:** Chưa đủ. Điều kiện tiền đề hầu như luôn sai, nên test có thể qua mà không hề kiểm tra trường hợp quan trọng. Generator cần chủ động sinh các cặp khác tham chiếu nhưng bằng nhau theo giá trị, cũng như ca null, khác giá trị và các bộ ba để kiểm tra bắc cầu.

### Bài 8 — `Objects.equals` và `equals(null)`

Vì sao `Objects.equals(null,null)` là `true` nhưng `new AccountKey("X",null).equals(null)` phải là `false`?

**Đáp án:** `Objects.equals` là hàm tiện ích so sánh **hai tham chiếu**, trong đó cả hai cùng `null` được xem là tương đương về tham chiếu. Còn `Object.equals` được gọi trên **một đối tượng có thật**; hợp đồng yêu cầu đối tượng đó không bằng `null`.

## 16. Checklist trước khi đưa value object vào ứng dụng

- [ ] Đã định nghĩa rõ **trường nào quyết định bằng nhau** theo nghiệp vụ và những trường nào được phép `null`.
- [ ] `equals` đúng phản xạ, đối xứng, bắc cầu, nhất quán và `x.equals(null) == false`.
- [ ] `hashCode` nhất quán với các trường/hợp đồng của `equals`; không yêu cầu hai đối tượng khác nhau phải có hash khác nhau.
- [ ] Có test nhiều thể hiện **khác tham chiếu nhưng bằng nhau theo giá trị**.
- [ ] Có test các trường hợp **khác một trường**, `null` và kiểu không liên quan.
- [ ] Có test `HashSet`, `HashMap`, và việc khóa không đổi trong thời gian lưu.
- [ ] Có test xác thực `null`, rỗng, biên và lỗi đúng loại tại constructor/factory.
- [ ] Dữ liệu mutable tham gia hợp đồng được quản lý bằng defensive copy hoặc chính sách bất biến rõ ràng.
- [ ] Mọi thay đổi mô hình dữ liệu, kế thừa hay normalization đều kéo theo rà soát `equals`, `hashCode` và test.
- [ ] Các API/cú pháp thuộc Java 9/10/11/16/17 được dùng đúng với baseline của dự án.

## 17. Tổng kết

Kiểm thử hợp đồng của đối tượng không dừng ở việc thấy `equals` trả đúng cho một cặp giá trị. Với Java hiện đại, nên kiểm tra **đủ năm tính chất của `equals`**, quy tắc **bằng nhau thì cùng hash**, hành vi thực tế trong `HashSet`/`HashMap`, và cách đối tượng phản ứng với **dữ liệu đầu vào hợp lệ hoặc không hợp lệ**. Các tiện ích `java.util.Objects` từ Java 7 như `Objects.equals`, `Objects.hash` và `Objects.requireNonNull` giúp implementation ngắn gọn, nhưng không thay thế việc thiết kế hợp đồng và kiểm thử.

Một value object đáng tin phải có **ngữ nghĩa so sánh rõ ràng, mã băm tương thích, dữ liệu đầu vào được xác thực sớm và trạng thái ổn định khi dùng làm khóa**. Chương trình Java 17+ ở mục 9 minh họa 18 phép kiểm tra có thể chạy trực tiếp; trong dự án lớn, có thể mở rộng thành unit test, parameterized test và property-based testing theo cùng các bất biến này.