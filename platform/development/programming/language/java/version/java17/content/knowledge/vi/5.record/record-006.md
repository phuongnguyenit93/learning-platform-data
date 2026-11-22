# Record trong Java 17: `equals()`, `hashCode()` và `toString()` được sinh tự động

Trong Java 17, **record** là một dạng class dành cho những đối tượng mà **trạng thái được mô tả bằng một tập thành phần dữ liệu (record components)**. Khi khai báo record, Java tự cung cấp các phương thức làm việc với giá trị, trong đó có **`equals(Object)`**, **`hashCode()`** và **`toString()`**. Đây là ba phương thức rất quan trọng khi so sánh đối tượng, dùng đối tượng làm khóa trong `HashMap`/phần tử của `HashSet`, hoặc quan sát dữ liệu khi chạy chương trình.

Bài học này giải thích **các phương thức đó được sinh như thế nào, so sánh những gì, giới hạn ở đâu, và khi nào nên tự định nghĩa lại**. Ví dụ dùng cú pháp chính thức của Java 17, không cần bật tính năng preview.

## 1. Vì sao record tự sinh ba phương thức này?

Với class thông thường, người lập trình hay phải tự viết constructor, các getter, `equals`, `hashCode` và `toString` để biểu diễn một nhóm dữ liệu:

```java
public final class PointClass {
    private final int x;
    private final int y;

    public PointClass(int x, int y) {
        this.x = x;
        this.y = y;
    }

    public int x() { return x; }
    public int y() { return y; }

    // Nếu muốn so sánh theo giá trị, còn phải viết equals và hashCode.
    // Nếu muốn in rõ dữ liệu, còn phải viết toString.
}
```

Nếu không ghi đè `equals()` ở class trên, `PointClass` sẽ kế thừa cách so sánh mặc định của `Object`: hai tham chiếu chỉ bằng nhau khi cùng trỏ đến một đối tượng. Trong khi đó, nhiều bài toán cần **hai điểm có cùng tọa độ được coi là bằng nhau dù là hai đối tượng được tạo riêng biệt**.

Với record, cách khai báo trở nên ngắn gọn:

```java
record Point(int x, int y) {
}
```

Từ **record header** `(int x, int y)`, Java cung cấp những thành phần tương ứng:

| Thành phần | Hành vi có sẵn |
| --- | --- |
| `Point(int x, int y)` | **Canonical constructor** khởi tạo các thành phần dữ liệu, nếu bạn không tự khai báo constructor tương ứng. |
| `x()`, `y()` | Các phương thức truy cập thành phần với tên trùng tên component; khác với kiểu getter `getX()`. |
| `equals(Object)` | So sánh **cùng kiểu record** và giá trị của **từng component**. |
| `hashCode()` | Sinh mã băm dựa trên các component, nhất quán với `equals`. |
| `toString()` | Tạo chuỗi mô tả record, gồm tên record và các component cùng giá trị của chúng. |

Các component tương ứng với các trường đối tượng `private final`. Record cũng là một class **ngầm định `final`** và **kế thừa `java.lang.Record`**. Do đó, record không thể được subclass bằng `extends`; đây không phải cơ chế tạo “data class có thể kế thừa”.

> **Điểm cốt lõi:** Khi nói ba phương thức “được sinh tự động”, nghĩa là người viết record không phải khai báo chúng để có hành vi mặc định. Record **vẫn có thể tự định nghĩa** một hoặc nhiều phương thức này khi có lý do rõ ràng.

## 2. Ví dụ đầu tiên: ba phương thức hoạt động ra sao?

Tạo tệp `RecordMethodsDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;

record Point(int x, int y) {
}

record OtherPoint(int x, int y) {
}

public class RecordMethodsDemo {
    public static void main(String[] args) {
        Point a = new Point(2, 5);
        Point b = new Point(2, 5);
        Point c = new Point(2, 6);

        System.out.println(a == b);
        System.out.println(a.equals(b));
        System.out.println(a.equals(c));
        System.out.println(a.equals(new OtherPoint(2, 5)));

        System.out.println(a.hashCode() == b.hashCode());
        System.out.println(a);

        Set<Point> points = new HashSet<>();
        points.add(a);
        System.out.println(points.contains(b));
    }
}
```

Biên dịch và chạy bằng JDK 17:

```bash
javac RecordMethodsDemo.java
java RecordMethodsDemo
```

Kết quả điển hình:

```text
false
true
false
false
true
Point[x=2, y=5]
true
```

Giải thích:

- `a == b` là `false`: `a` và `b` là **hai đối tượng riêng**, nên không cùng tham chiếu.
- `a.equals(b)` là `true`: cả hai cùng là `Point`, có `x = 2` và `y = 5`.
- `a.equals(c)` là `false`: component `y` khác nhau.
- `a.equals(new OtherPoint(2, 5))` là `false`: có cùng hình dạng và giá trị nhưng **khác loại record**.
- Hai `Point` bằng nhau có cùng `hashCode()`.
- `System.out.println(a)` gọi `a.toString()` để hiển thị các component.
- `HashSet` nhận ra một `Point` khác nhưng bằng `a` theo giá trị, nên `contains(b)` là `true`.

**Không nên ghi nhớ một con số hash cụ thể** cho `Point(2, 5)`. Hợp đồng quan trọng là **các record bằng nhau có cùng mã băm**, không phải một công thức số học cố định trong mọi phiên bản JDK.

## 3. `equals(Object)`: so sánh theo thành phần, không phải địa chỉ đối tượng

Khai báo:

```java
record Student(String name, int age, boolean active) {
}
```

Nếu không tự ghi đè, `Student` có một `equals(Object)` với ý nghĩa:

1. Đối tượng được so sánh phải là **cùng loại record `Student`**.
2. Các component tương ứng (`name`, `age`, `active`) phải bằng nhau.
3. Nếu có component khác nhau thì hai record không bằng nhau.

Trong ví dụ này:

```java
Student s1 = new Student("Lan", 20, true);
Student s2 = new Student("Lan", 20, true);
Student s3 = new Student("lan", 20, true);

System.out.println(s1.equals(s2)); // true
System.out.println(s1.equals(s3)); // false: String.equals phân biệt chữ hoa/thường
System.out.println(s1.equals(null)); // false
```

Với kiểu tham chiếu như `String`, cách so sánh tuân theo **`equals` của kiểu giá trị component đó**, có xử lý `null`. Với component nguyên thủy, Java dùng quy tắc so sánh giá trị thích hợp với kiểu nguyên thủy; riêng `float` và `double` cần chú ý trường hợp đặc biệt bên dưới.

### 3.1. So sánh component primitive và reference

| Kiểu component | Hành vi quan trọng của `equals()` sinh tự động |
| --- | --- |
| `int`, `long`, `short`, `byte`, `char`, `boolean` | So sánh giá trị nguyên thủy tương ứng. |
| `float`, `double` | So sánh theo ngữ nghĩa của `Float.compare`/`Double.compare`, có phân biệt số không mang dấu khác nhau và xử lý `NaN`. |
| `String` | So sánh theo `String.equals`, phân biệt chữ hoa/chữ thường. |
| `BigDecimal` | Dùng `BigDecimal.equals`: `1.0` và `1.00` **không** bằng nhau theo `equals` do khác scale. |
| `List<T>` | Theo `List.equals`: thường so sánh từng phần tử theo thứ tự và theo hợp đồng `equals` của chúng. |
| Mảng `int[]`, `String[]`, ... | Theo cách so sánh tham chiếu của mảng; **không tự so sánh từng phần tử**. |

Đối với `double`, hai trường hợp dễ gây bất ngờ:

```java
record Measure(double value) {
}

System.out.println(
        new Measure(+0.0).equals(new Measure(-0.0))
); // false

System.out.println(
        new Measure(Double.NaN).equals(new Measure(Double.NaN))
); // true
```

Điều này khác với phép `==` nguyên thủy trên `double`: `+0.0 == -0.0` là `true`, còn `Double.NaN == Double.NaN` là `false`. Quy tắc của record hỗ trợ hợp đồng nhất quán giữa `equals` và `hashCode`.

### 3.2. Mảng là trường hợp cần đặc biệt lưu ý

```java
import java.util.Arrays;

record Scores(int[] values) {
}

int[] first = {8, 9, 10};
int[] second = {8, 9, 10};

Scores a = new Scores(first);
Scores b = new Scores(second);
Scores c = new Scores(first);

System.out.println(Arrays.equals(first, second)); // true
System.out.println(a.equals(b)); // false
System.out.println(a.equals(c)); // true
```

**Vì sao?** `Arrays.equals(first, second)` so sánh nội dung hai mảng. Nhưng mặc định `equals` của record dùng hành vi so sánh tham chiếu cho component mảng: hai biến trỏ tới **hai mảng khác nhau**, dù bên trong có các phần tử giống hệt, thì không được coi là cùng component.

Khi record chứa mảng, bạn cần chọn một trong hai hướng:

- Thực sự muốn dùng **định danh mảng**: giữ hành vi mặc định, hiểu rõ giới hạn.
- Muốn dùng **giá trị các phần tử**: chuyển sang kiểu collection có `equals` theo nội dung phù hợp, hoặc tự thiết kế `equals`/`hashCode` cho component mảng.

Đừng giả định từ khóa `record` tự động thực hiện so sánh sâu (`deep equality`) cho mọi cấu trúc dữ liệu lồng nhau.

### 3.3. Hai record khác loại không bằng nhau chỉ vì cùng component

```java
record UserId(long value) {
}

record OrderId(long value) {
}

System.out.println(new UserId(100).equals(new OrderId(100))); // false
```

Đây là một đặc tính có ích: các giá trị thuộc hai khái niệm miền nghiệp vụ khác nhau vẫn giữ **ranh giới loại dữ liệu** mặc dù bên trong dùng cùng kiểu `long`.

## 4. `hashCode()`: mã băm dựa trên các component

Khi không tự định nghĩa `hashCode`, Java sinh mã băm phù hợp với cách so sánh component của record. Đối với hai record cùng loại và bằng nhau theo `equals`, mã băm phải bằng nhau:

```java
record Book(String isbn, int edition) {
}

Book book1 = new Book("978-0-00-000000-0", 2);
Book book2 = new Book("978-0-00-000000-0", 2);

System.out.println(book1.equals(book2)); // true
System.out.println(book1.hashCode() == book2.hashCode()); // true
```

Các nguyên tắc cần nhớ:

1. **`a.equals(b)` là `true` thì `a.hashCode() == b.hashCode()` phải là `true`.**
2. **Hai mã băm bằng nhau không chứng minh hai đối tượng bằng nhau**; va chạm mã băm có thể xảy ra.
3. Mã băm không phải ID duy nhất, checksum an toàn hay giá trị nên lưu cố định làm khóa bên ngoài ứng dụng.
4. Không nên phụ thuộc vào **giá trị số hoặc công thức** `hashCode()` do JDK sinh; hợp đồng tương thích nằm ở quan hệ giữa `equals` và `hashCode`.

### Vì sao quan trọng với `HashSet` và `HashMap`?

```java
import java.util.HashMap;
import java.util.Map;

record ProductKey(String sku, int warehouseId) {
}

Map<ProductKey, Integer> stock = new HashMap<>();
stock.put(new ProductKey("P100", 3), 12);

int available = stock.get(new ProductKey("P100", 3));
System.out.println(available); // 12
```

Chương trình tạo **hai đối tượng `ProductKey` riêng** nhưng có cùng component. `HashMap` vẫn tìm đúng phần tử vì record có `equals` và `hashCode` tương thích theo giá trị. Đây là một lý do phổ biến để dùng record cho **khóa tổng hợp**.

Tuy nhiên, nếu component tham chiếu tới một đối tượng có thể thay đổi trạng thái sau khi record được dùng làm khóa, kết quả tra cứu có thể trở nên không ổn định. Sự bất biến của **tham chiếu** không đồng nghĩa bất biến sâu của dữ liệu nằm bên trong nó.

## 5. `toString()`: hiển thị rõ tên record và component

Cho record:

```java
record Address(String city, String country) {
}

Address address = new Address("Hà Nội", "Việt Nam");
System.out.println(address.toString());
System.out.println(address);
```

Trên các JDK 17 thông dụng, hai lệnh trên thường hiển thị:

```text
Address[city=Hà Nội, country=Việt Nam]
Address[city=Hà Nội, country=Việt Nam]
```

Điều này có ích khi kiểm tra dữ liệu trong lúc phát triển mà không cần tự nối chuỗi. `println(Object)` dùng `String.valueOf`, từ đó gọi `toString()` khi đối tượng không phải `null`.

**Đừng coi định dạng chuỗi cụ thể là hợp đồng dữ liệu lâu dài.** Đặc tả yêu cầu chuỗi cung cấp tên record và thông tin component, nhưng chi tiết định dạng có thể phụ thuộc triển khai. Không nên phân tích cú pháp `toString()` để trao đổi dữ liệu với hệ thống khác; hãy dùng định dạng trao đổi phù hợp như JSON và serializer thích hợp.

### 5.1. Trường tham chiếu và `null`

```java
record Profile(String nickname, Integer level) {
}

System.out.println(new Profile(null, 3));
// Ví dụ: Profile[nickname=null, level=3]
```

Record **không tự cấm `null`**. Nếu muốn cấm, hãy kiểm tra trong constructor. Với dữ liệu lồng nhau, `toString()` của record sử dụng dạng biểu diễn chuỗi tương ứng của các giá trị component, nên việc dễ đọc phụ thuộc cả vào kiểu component.

### 5.2. `toString()` không bảo đảm an toàn cho dữ liệu nhạy cảm

```java
record AccessToken(String account, String token) {
    @Override
    public String toString() {
        return "AccessToken[account=" + account + ", token=***]";
    }
}
```

Nếu để `toString` mặc định, chuỗi token có thể xuất hiện trong log khi in record. Ghi đè `toString()` như trên giúp tránh **vô tình log bí mật qua phương thức này**. Dù vậy, nó **không ẩn dữ liệu khỏi accessor** `token()` và không thay thế việc quản lý bí mật đúng cách.

## 6. `final` ở component không có nghĩa “bất biến sâu”

Các field tương ứng với record components là `private final`, nghĩa là **không thể gán lại tham chiếu của field sau khởi tạo**. Nhưng nếu bản thân đối tượng component có thể thay đổi, nội dung vẫn có thể bị sửa:

```java
import java.util.ArrayList;
import java.util.List;

record Basket(List<String> items) {
}

List<String> list = new ArrayList<>();
list.add("Bút");

Basket basket = new Basket(list);
System.out.println(basket); // Basket[items=[Bút]]

list.add("Vở");
System.out.println(basket); // Basket[items=[Bút, Vở]]
```

Giá trị quan sát được qua `toString()` **thay đổi**, và kết quả `hashCode()` cũng có thể thay đổi theo nội dung của `List`. Nếu đã đưa `basket` vào một `HashSet` hoặc dùng nó làm khóa `HashMap` trước khi sửa list, hành vi tìm kiếm có thể không còn đúng như kỳ vọng.

### 6.1. Sao chép dữ liệu trong constructor

Một cách thiết kế an toàn hơn cho dữ liệu collection là tạo bản sao không cho sửa qua các thao tác thông thường:

```java
import java.util.List;
import java.util.Objects;

record ImmutableBasket(List<String> items) {
    ImmutableBasket {
        Objects.requireNonNull(items, "items");
        items = List.copyOf(items);
    }
}
```

Trong **compact constructor**, tham số `items` có thể được chuẩn hóa trước khi Java gán vào field tương ứng; không cần tự viết `this.items = items`. `List.copyOf` trả về một list không cho thay đổi cấu trúc và các phần tử của nó qua những thao tác trên list, đồng thời không cho phép phần tử `null`. Ví dụ dùng `String` là kiểu bất biến nên cấu trúc này phù hợp để dùng làm value object.

```java
List<String> source = new ArrayList<>();
source.add("Bút");

ImmutableBasket safe = new ImmutableBasket(source);
source.add("Vở");

System.out.println(safe); // ImmutableBasket[items=[Bút]]
```

**Giới hạn:** `List.copyOf` là sao chép ở mức collection; nếu từng phần tử vẫn là đối tượng mutable, các đối tượng phần tử đó có thể tiếp tục bị thay đổi qua tham chiếu khác. Bất biến sâu đòi hỏi xem xét toàn bộ đồ thị dữ liệu chứ không chỉ lớp vỏ `record`.

### 6.2. Với mảng, sao chép phòng vệ chưa đủ để đổi `equals`

Ngay cả khi clone mảng trong constructor và khi trả accessor, `equals` mặc định của record vẫn xem component mảng như **tham chiếu**, không tự so sánh phần tử. Nếu cần ngữ nghĩa giá trị theo nội dung mảng, phải thiết kế lại cả `equals()` và `hashCode()` phù hợp, hoặc chọn kiểu dữ liệu khác.

## 7. Khi nào nên tự định nghĩa lại các phương thức?

Record ưu tiên ngữ nghĩa **giá trị của toàn bộ các component**. Vì vậy, giữ phương thức mặc định thường là lựa chọn tốt khi các component thật sự tạo nên bản sắc của value object và có `equals` ổn định.

Tự định nghĩa có thể hợp lý khi:

- Cần che một component nhạy cảm hoặc biểu diễn chuỗi theo định dạng đặc biệt → **chỉ ghi đè `toString()`**.
- Cần so sánh nội dung mảng thay cho tham chiếu → **ghi đè cả `equals()` và `hashCode()`** và chú ý sao chép phòng vệ.
- Cần thay đổi cách định nghĩa giá trị bằng nhau → **thiết kế lại `equals()` cùng `hashCode()`**; cân nhắc liệu record còn thích hợp với mô hình hay không.
- Cần chuẩn hóa dữ liệu trước khi so sánh → thường nên **chuẩn hóa trong constructor** để giữ các phương thức mặc định, thay vì tự viết lại ba phương thức.

### 7.1. Ưu tiên chuẩn hóa component nếu có thể

Ví dụ muốn email không phân biệt chữ hoa/chữ thường **theo chính sách của ứng dụng**:

```java
import java.util.Locale;
import java.util.Objects;

record NormalizedEmail(String value) {
    NormalizedEmail {
        value = Objects.requireNonNull(value, "value")
                .strip()
                .toLowerCase(Locale.ROOT);
    }
}
```

```java
NormalizedEmail a = new NormalizedEmail(" User@Example.COM ");
NormalizedEmail b = new NormalizedEmail("user@example.com");

System.out.println(a.equals(b)); // true
System.out.println(a.hashCode() == b.hashCode()); // true
```

Vì cả hai đối tượng **lưu component đã chuẩn hóa như nhau**, `equals`, `hashCode` và `toString` mặc định đã nhất quán. Đây là ví dụ về quy tắc chuẩn hóa do ứng dụng lựa chọn; không nên mặc định áp dụng cùng phép chuyển chữ thường cho mọi loại định danh hoặc dữ liệu quốc tế.

### 7.2. Ví dụ tự định nghĩa cả `equals` và `hashCode` cho mảng

Tạo tệp `IntVectorDemo.java`:

```java
import java.util.Arrays;

record IntVector(int[] elements) {
    IntVector {
        elements = elements.clone();
    }

    @Override
    public int[] elements() {
        return elements.clone();
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof IntVector vector
                && Arrays.equals(elements, vector.elements);
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(elements);
    }

    @Override
    public String toString() {
        return "IntVector[elements=" + Arrays.toString(elements) + "]";
    }
}

public class IntVectorDemo {
    public static void main(String[] args) {
        int[] source = {1, 2, 3};
        IntVector first = new IntVector(source);
        IntVector second = new IntVector(new int[] {1, 2, 3});

        source[0] = 99;
        first.elements()[1] = 88;

        System.out.println(first.equals(second));
        System.out.println(first.hashCode() == second.hashCode());
        System.out.println(first);
    }
}
```

Chạy:

```bash
javac IntVectorDemo.java
java IntVectorDemo
```

Kết quả:

```text
true
true
IntVector[elements=[1, 2, 3]]
```

Ví dụ này kết hợp **ba quyết định thiết kế**:

1. Constructor clone mảng để mã bên ngoài không thể sửa dữ liệu bên trong qua mảng đầu vào.
2. Accessor `elements()` cũng clone mảng để bên ngoài không thể sửa dữ liệu qua giá trị trả về.
3. `equals` và `hashCode` đều dùng logic của `Arrays`, trong khi `toString` chủ động in danh sách phần tử.

`Arrays.equals` và `Arrays.hashCode` phù hợp với mảng một chiều chứa `int`. Đối với **mảng lồng nhau**, hãy cân nhắc `Arrays.deepEquals` và `Arrays.deepHashCode`, đồng thời xử lý sao chép sâu nếu dữ liệu bên trong cũng cần bất biến. Không nên dùng `Arrays.equals` với ý định so sánh sâu mọi tầng một cách mặc định.

### 7.3. Nếu chỉ dùng một component để quyết định bằng nhau

Mặc định, record so sánh **tất cả** component. Bạn có thể ghi đè để dùng một tập component khác, nhưng điều đó thay đổi ý nghĩa của kiểu:

```java
import java.util.Objects;

record Employee(String id, String displayName) {
    Employee {
        Objects.requireNonNull(id, "id");
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof Employee employee
                && id.equals(employee.id);
    }

    @Override
    public int hashCode() {
        return id.hashCode();
    }
}
```

Hai `Employee` cùng `id` nhưng khác `displayName` sẽ bằng nhau theo định nghĩa mới. Việc này có thể được lựa chọn trong một số mô hình, nhưng cũng dễ gây bất ngờ vì record header liệt kê **cả hai** component. Nếu thực thể có định danh và vòng đời thay đổi, class thông thường có thể diễn đạt mô hình rõ hơn. Khi tự định nghĩa, phải bảo đảm mọi quy tắc của `equals` và `hashCode` vẫn đúng.

## 8. Hợp đồng của `equals` và `hashCode` khi ghi đè

Các nguyên tắc này áp dụng cho mọi class trong Java, gồm record:

| Quy tắc | Ý nghĩa |
| --- | --- |
| Phản xạ | `a.equals(a)` phải là `true` với đối tượng khác `null`. |
| Đối xứng | `a.equals(b)` và `b.equals(a)` phải cho cùng kết quả. |
| Bắc cầu | Nếu `a.equals(b)` và `b.equals(c)` thì `a.equals(c)`. |
| Nhất quán | Khi những dữ liệu dùng cho so sánh không đổi, kết quả `equals` phải nhất quán. |
| So sánh với `null` | `a.equals(null)` phải là `false`. |
| Quan hệ hash | `a.equals(b)` là `true` thì `a.hashCode() == b.hashCode()` phải đúng. |

**Phương thức mặc định của record** đã tuân thủ các hợp đồng cần thiết với các component có hành vi tương thích. Khi ghi đè `equals`, không được giả định `hashCode` tự sinh vẫn phù hợp với cách so sánh mới.

Ví dụ lỗi thiết kế:

```java
// Ví dụ minh họa lỗi: KHÔNG nên dùng trong ứng dụng.
record BadKey(String code, String label) {
    @Override
    public boolean equals(Object other) {
        return other instanceof BadKey key && code.equals(key.code);
    }

    // hashCode vẫn được sinh theo các component của record.
    // Hai BadKey cùng code nhưng khác label được coi là bằng nhau,
    // song hashCode mặc định có thể khác nhau => vi phạm hợp đồng.
}
```

Nếu muốn so sánh chỉ theo `code`, phải định nghĩa `hashCode` tương ứng theo `code`, hoặc chọn cách thiết kế không cần thay đổi ngữ nghĩa so sánh mặc định.

## 9. Những điều record không tự làm

Ba phương thức được sinh tự động rất hữu ích, nhưng **không phải tất cả nhu cầu mô hình dữ liệu đều được giải quyết**:

| Điều dễ hiểu nhầm | Hành vi thực tế |
| --- | --- |
| “Record so sánh sâu toàn bộ dữ liệu.” | Với mảng, `equals` mặc định vẫn so sánh tham chiếu; với object khác, dùng hợp đồng `equals` của object đó. |
| “Mọi thứ trong record đều bất biến.” | Field là `final`, nhưng object được tham chiếu có thể mutable. |
| “Mã băm của record là hằng số được quy định.” | Chỉ quan hệ tương thích với `equals` được bảo đảm; không phụ thuộc vào số hash cụ thể. |
| “`toString()` luôn an toàn để đưa vào log.” | Có thể chứa dữ liệu nhạy cảm từ component. |
| “Hai record có cùng tên component/giá trị thì bằng nhau.” | Phải cùng loại record; cùng cấu trúc không có nghĩa bằng nhau. |
| “Constructor record tự kiểm tra dữ liệu hợp lệ.” | Muốn cấm `null`, số âm hoặc giá trị không phù hợp phải kiểm tra hay chuẩn hóa. |
| “`toString()` có thể dùng làm định dạng lưu trữ ổn định.” | Định dạng chi tiết không nên được coi là giao thức trao đổi dữ liệu. |

## 10. Khi nào dùng record cho value object?

Record thích hợp khi đối tượng là **một nhóm giá trị được xác định chủ yếu bởi các component**. Một số ví dụ:

- **Tọa độ:** `record Point(int x, int y)`.
- **Phạm vi ngày:** `record DateRange(LocalDate start, LocalDate end)`; cần tự kiểm tra `start` không sau `end`.
- **Khóa dữ liệu tổng hợp:** `record OrderKey(String orderId, int lineNumber)`.
- **Kết quả tính toán:** `record Result(int total, boolean successful)`.
- **Dữ liệu truyền giữa các lớp:** `record SearchResult(String title, int score)` nếu các component tạo nên ngữ nghĩa của giá trị.

Nếu bạn cần **đối tượng có định danh riêng, trạng thái thay đổi liên tục**, hoặc kỳ vọng phần lớn thuộc tính không tham gia định nghĩa sự bằng nhau, class thông thường có thể thích hợp hơn. Không nên ép mọi đối tượng Java thành record chỉ để giảm số dòng code.

## 11. Bài tập tự luyện

### Bài tập 1: dự đoán ba phương thức

```java
record Size(int width, int height) {
}

Size s1 = new Size(10, 20);
Size s2 = new Size(10, 20);
Size s3 = new Size(20, 10);
```

Hãy dự đoán:

1. `s1 == s2` là gì?
2. `s1.equals(s2)` và `s1.equals(s3)` là gì?
3. `s1.hashCode() == s2.hashCode()` có chắc chắn đúng không?
4. `System.out.println(s1)` có thể hiển thị thông tin nào?

**Gợi ý:** Trả lời lần lượt `false`, `true`/`false`, `true`, và chuỗi có tên record cùng tên/giá trị `width`, `height` (thường là `Size[width=10, height=20]`).

### Bài tập 2: mảng có làm so sánh theo nội dung không?

```java
record Pixels(int[] rgb) {
}

Pixels p1 = new Pixels(new int[] {255, 0, 0});
Pixels p2 = new Pixels(new int[] {255, 0, 0});
```

Giải thích vì sao `p1.equals(p2)` không trả về `true` theo giá trị từng phần tử. Hãy sửa thiết kế bằng **`Arrays.equals` và `Arrays.hashCode`**, đồng thời cân nhắc sao chép phòng vệ mảng trong constructor/accessor.

### Bài tập 3: tránh thay đổi hash khi làm khóa map

```java
record FilterKey(java.util.List<String> tags) {
}
```

Hãy xây dựng constructor dùng `List.copyOf(tags)`, sau đó đặt một `FilterKey` vào `HashMap`. Thử thay đổi list nguồn; giải thích vì sao bản sao không cho sửa giúp kết quả `equals` và `hashCode` ổn định hơn khi component là danh sách `String`.

### Bài tập 4: thiết kế cách hiển thị an toàn

Thiết kế `record LoginSession(String userId, String sessionToken)` và ghi đè **chỉ** `toString()` để không in nguyên token trong log. Xác nhận rằng `equals` và `hashCode` vẫn do Java sinh từ cả hai component nếu bạn không ghi đè chúng.

## 12. Ghi nhớ khi áp dụng

**`equals()`** của record mặc định biểu diễn sự bằng nhau dựa trên **cùng loại record và giá trị từng component**. **`hashCode()`** tự sinh nhất quán với cách so sánh đó, đặc biệt hữu ích cho `HashSet` và `HashMap`. **`toString()`** giúp quan sát tên record cùng các component mà không cần tự ghép chuỗi. Khi component có thể thay đổi, là mảng, chứa bí mật, hoặc khi định nghĩa “bằng nhau” không giống việc so sánh tất cả component, hãy chủ động thiết kế constructor, các accessor và phương thức ghi đè tương ứng.

### Tài liệu tham khảo

- [JEP 395: Records](https://openjdk.org/jeps/395) — record trở thành tính năng chính thức của Java.
- [Java Language Specification, Java SE 17 — §8.10 Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10) — đặc tả record, constructor, component và các phương thức mặc định.
- [Java SE 17 API — `java.lang.Record`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html) — lớp nền của mọi record và hợp đồng về giá trị.
- [Java SE 17 API — `java.util.Arrays`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html) — phương thức so sánh, tạo hash và biểu diễn chuỗi cho mảng.
- [Java SE 17 API — `java.util.List`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)) — `List.copyOf` để tạo collection không cho sửa qua các thao tác thông thường.
