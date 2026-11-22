# Khóa trùng và giá trị thay thế khi gọi `Map.put()`

Khi làm việc với cấu trúc dữ liệu băm trong Java, `Map.put(key, value)` không đơn giản là “thêm một phần tử”. Nếu map **chưa có khóa tương đương**, thao tác sẽ tạo ánh xạ mới. Nếu map **đã có khóa tương đương**, thao tác sẽ **thay giá trị gắn với khóa hiện có**. Đây là hành vi quan trọng của `HashMap` và là nền tảng để hiểu vì sao hai đối tượng khóa khác nhau về danh tính vẫn có thể cùng đại diện cho một entry.

Ví dụ: sau `scores.put("java", 10)`, gọi `scores.put("java", 20)` thì giá trị của khóa `"java"` trở thành `20`, số entry không tăng, và lần gọi thứ hai trả về giá trị cũ `10`. Để hiểu đầy đủ, cần làm rõ **khóa trùng được xác định ra sao**, **`hashCode` và `equals` phối hợp như thế nào**, **`put` trả về gì**, và **`null` làm thay đổi cách đọc kết quả ra sao**.

## 1. Ý nghĩa và hợp đồng cơ bản của `Map.put()`

Khai báo khái quát của phương thức trong giao diện `Map<K, V>`:

~~~java
V put(K key, V value);
~~~

`put` gắn một `value` với `key`; nếu trước đó map đã chứa ánh xạ cho khóa này, giá trị mới thay thế giá trị cũ. Giá trị trả về là **giá trị trước đó** của khóa, hoặc `null` nếu trước đó không có ánh xạ; một `null` cũng có thể có nghĩa **giá trị cũ vốn là `null`** trong các map cho phép `null`.

| Tình trạng trước `put(k, v)` | Sau khi gọi | Giá trị trả về | Kích thước map |
| --- | --- | --- | --- |
| Chưa có khóa tương đương `k` | Tạo ánh xạ `k → v` | `null` | Tăng 1 |
| Đã có `k → old`, `old != null` | Đổi thành `k → v` | `old` | Giữ nguyên |
| Đã có `k → null` và map cho phép giá trị null | Đổi thành `k → v` | `null` | Giữ nguyên |

`put` là thao tác sửa đổi. Không phải mọi hiện thực `Map` đều hỗ trợ: chẳng hạn map tạo bằng `Map.of(...)` không thể sửa, nên gọi `put` sẽ ném `UnsupportedOperationException`. Các ví dụ trong bài chủ yếu dùng **`HashMap` có thể sửa đổi**.

Với `HashMap`, **mỗi khóa phân biệt theo `equals` chỉ có một entry**, không phụ thuộc có bao nhiêu lần gán lại giá trị cho khóa đó. Thay giá trị **không** làm tăng kích thước. Ngược lại, có thêm khóa mới thì `size()` tăng kể cả giá trị mới trùng với giá trị của khóa khác: tính duy nhất áp dụng cho **khóa**, không phải cho **value**.

## 2. Hai đối tượng khóa độc lập vẫn có thể được coi là khóa trùng

Một nhầm lẫn thường gặp là nghĩ chỉ các tham chiếu cùng đối tượng (`==`) mới có thể thay thế cùng entry. Với `HashMap`, khóa được tìm qua hash và kiểm tra bằng nhau theo `equals`. Do đó, **hai đối tượng độc lập** có thể đại diện cho **cùng khóa logic**, miễn là `equals`/`hashCode` được định nghĩa đúng.

Giả sử `ProductKey` nhận diện sản phẩm bằng `sku`. Hai `ProductKey("P-01")` được tạo riêng nhưng biểu diễn cùng mã sản phẩm. `record` trong Java 17 sinh sẵn `equals` và `hashCode` dựa trên thành phần `sku`.

Tệp **`MapPutDemo.java`**, chạy độc lập trên Java 17+:

~~~java
import java.util.HashMap;
import java.util.Map;

public class MapPutDemo {
    record ProductKey(String sku) {}

    public static void main(String[] args) {
        Map<ProductKey, String> products = new HashMap<>();

        ProductKey first = new ProductKey("P-01");
        ProductKey sameValue = new ProductKey("P-01");
        ProductKey other = new ProductKey("P-02");

        System.out.println(first == sameValue);
        System.out.println(first.equals(sameValue));
        System.out.println(first.hashCode() == sameValue.hashCode());

        System.out.println(products.put(first, "Draft"));
        System.out.println(products.put(other, "Active"));
        System.out.println(products.size());

        System.out.println(products.put(sameValue, "Published"));
        System.out.println(products.size());
        System.out.println(products.get(first));
        System.out.println(products.get(sameValue));
        System.out.println(products.get(other));

        System.out.println(products.put(first, "Archived"));
        System.out.println(products.get(sameValue));
        System.out.println(products.size());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac MapPutDemo.java
java MapPutDemo
~~~

Kết quả chính xác:

~~~text
false
true
true
null
null
2
Draft
2
Published
Published
Active
Published
Archived
2
~~~

Giải thích từng nhóm kết quả:

1. `first == sameValue` là `false` vì đây là hai instance được tạo độc lập. Nhưng `first.equals(sameValue)` là `true` vì cả hai record có cùng `sku`. Khi `equals` là `true`, hợp đồng buộc `hashCode` tương ứng phải bằng nhau.
2. `put(first, "Draft")` và `put(other, "Active")` đều trả `null` vì trước đó chưa có ánh xạ tương ứng. Map lúc này có **2 entry**.
3. `put(sameValue, "Published")` trả về **`"Draft"`**, là giá trị cũ của khóa `"P-01"`. Tuy `sameValue` không cùng tham chiếu với `first`, chúng bằng nhau theo hợp đồng của `ProductKey`, nên entry được cập nhật, không tạo entry thứ ba. `size()` vẫn là `2`.
4. Cả `get(first)` và `get(sameValue)` đều trả `"Published"`. `get(other)` vẫn trả `"Active"` vì `"P-02"` là khóa riêng.
5. `put(first, "Archived")` trả `"Published"`. Sau đó, `get(sameValue)` trả `"Archived"` và kích thước vẫn là `2`.

Điểm cốt lõi: **`put` quyết định “khóa đã tồn tại hay chưa” theo ngữ nghĩa khóa của map**, không dựa đơn thuần vào việc biến khóa là một đối tượng được tạo mới.

### Hash code tham gia ở bước nào?

Trong `HashMap`, hash code giúp định vị nhóm ứng viên cần tra cứu. Sau đó map cần kiểm tra sự bằng nhau của khóa để biết ứng viên nào đại diện cho cùng khóa logic. Với một lớp khóa bình thường:

- `k1.equals(k2) == true` thì **bắt buộc** `k1.hashCode() == k2.hashCode()`. Nếu vi phạm, thao tác `put` hoặc `get` có thể không tìm ra entry tương đương.
- `k1.hashCode() == k2.hashCode()` **không suy ra** `k1.equals(k2)`. Hai khóa khác nhau vẫn được phép trùng hash; `HashMap` phải phân biệt chúng.

Những chi tiết như số bucket, cách trộn bit hay cấu trúc nội bộ khi va chạm là chi tiết triển khai. Điều mà mã ứng dụng cần dựa vào là **hợp đồng khóa** và hành vi `Map` đã công bố, không phải giả định về vị trí bucket.

## 3. Khóa trùng khác với hash collision

Hai chuỗi `"Aa"` và `"BB"` có **cùng** `String.hashCode() == 2112`, nhưng không bằng nhau về nội dung. Khi lần lượt đưa chúng vào `HashMap`, **cả hai entry vẫn tồn tại**.

~~~java
Map<String, Integer> scores = new HashMap<>();

scores.put("Aa", 10);
scores.put("BB", 20);

System.out.println("Aa".hashCode() == "BB".hashCode()); // true
System.out.println("Aa".equals("BB"));                  // false
System.out.println(scores.size());                      // 2
System.out.println(scores.get("Aa"));                   // 10
System.out.println(scores.get("BB"));                   // 20
~~~

Đoạn trên là phần mã minh họa đặt **bên trong một phương thức**, với `import java.util.HashMap;` và `import java.util.Map;` nếu biên dịch riêng. Chú thích phản ánh output đúng của Java.

Nếu tiếp tục `scores.put(new String("Aa"), 30)`, chỉ giá trị của entry khóa `"Aa"` đổi thành `30`; entry `"BB"` giữ `20`, và kích thước vẫn là `2`. Đây là **trùng khóa theo `equals`**, khác với **trùng mã băm**.

| Trường hợp | `equals` của hai key | Hash code | `put` vào `HashMap` |
| --- | --- | --- | --- |
| Hai `ProductKey("P-01")` | `true` | Phải bằng nhau | Key sau cập nhật value của entry cũ |
| `"Aa"` và `"BB"` | `false` | Đều bằng `2112` | Giữ hai entry khác nhau |
| `"P-01"` và `"P-02"` | `false` | Có thể khác hoặc trùng | Giữ hai entry khác nhau |

**Không được lấy `hashCode` làm mã khóa duy nhất** trong nghiệp vụ. Nếu tự thay `Map<ProductKey, ...>` bằng `Map<Integer, ...>` chỉ lưu hash của key, bạn có thể khiến hai khóa không bằng nhau bị gộp nhầm.

## 4. Giá trị trả về của `put` và cái bẫy `null`

Với `HashMap`, bạn có thể lưu **khóa `null`** và **giá trị `null`**. Điều này tạo ra một điểm cần chú ý: chỉ nhìn kết quả trả về `null` của `put` là **không đủ để biết** vừa thêm khóa mới hay vừa thay một value cũ vốn bằng `null`.

Tệp **`MapNullAndCollisionDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class MapNullAndCollisionDemo {
    public static void main(String[] args) {
        Map<String, String> states = new HashMap<>();

        System.out.println(states.put("task", null));
        System.out.println(states.containsKey("task"));
        System.out.println(states.size());

        System.out.println(states.put("task", "Queued"));
        System.out.println(states.size());
        System.out.println(states.get("task"));

        System.out.println(states.put("task", "Done"));
        System.out.println(states.get("task"));
        System.out.println(states.containsKey("missing"));
        System.out.println(states.get("missing"));

        Map<String, Integer> numbers = new HashMap<>();
        System.out.println(numbers.put(null, 1));
        System.out.println(numbers.put(null, 2));
        System.out.println(numbers.size());
        System.out.println(numbers.get(null));

        numbers.put("Aa", 10);
        numbers.put("BB", 20);
        System.out.println("Aa".hashCode() == "BB".hashCode());
        System.out.println(numbers.size());
        System.out.println(numbers.get("Aa"));
        System.out.println(numbers.get("BB"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac MapNullAndCollisionDemo.java
java MapNullAndCollisionDemo
~~~

Kết quả chính xác:

~~~text
null
true
1
null
1
Queued
Queued
Done
false
null
null
1
1
2
true
3
10
20
~~~

Diễn giải:

- Gọi `states.put("task", null)` trên map trống trả về `null`, **nhưng map đã có khóa `"task"`**: `containsKey("task")` là `true`, `size() == 1`.
- Gọi `states.put("task", "Queued")` cũng trả về `null`, lần này vì **giá trị cũ là `null`**. Đây là một lần **thay thế**, nên kích thước vẫn là `1`.
- Gọi `states.put("task", "Done")` trả về `"Queued"`; `get("task")` là `"Done"`.
- Với khóa `"missing"`, `containsKey` là `false`, còn `get` là `null`. Vì thế không nên dùng một mình `get(k) == null` để khẳng định key không tồn tại trong map cho phép giá trị `null`.
- Trong `HashMap`, khóa `null` được chấp nhận. Lần `put(null, 2)` thay thế `put(null, 1)`, trả `1`, và map `numbers` vẫn chỉ có một entry trước khi thêm hai chuỗi.
- `"Aa"` và `"BB"` cùng hash code nhưng khác `equals`, nên đều được thêm vào `numbers`; cùng với entry có khóa `null`, tổng là **3 entry**.

Nếu cần biết chắc một khóa đã tồn tại **trước khi gọi** `put`, có thể dùng `containsKey` trước thao tác:

~~~java
boolean existedBefore = states.containsKey("task");
String previous = states.put("task", "Reviewed");
~~~

Đây là ví dụ cho việc phân biệt trạng thái trước/sau **trong luồng thao tác đơn giản, không có cập nhật cạnh tranh**. Trong chương trình đa luồng, cặp `containsKey` rồi `put` **không tạo thành một thao tác nguyên tử**; phải dùng hiện thực/construction hỗ trợ đồng bộ hoặc các thao tác nguyên tử thích hợp khi cần. Ngoài ra, một số `Map` không cho khóa hoặc giá trị `null`: `Map.of` không chấp nhận `null`; `ConcurrentHashMap` cũng không chấp nhận khóa/giá trị `null`. Không nên suy rộng ví dụ `HashMap` sang mọi hiện thực `Map`.

## 5. `put`, `putIfAbsent` và `replace` khác nhau ở đâu?

Ba phương thức này có chủ đích khác nhau:

| Phương thức | Hành vi chính |
| --- | --- |
| `put(k, v)` | Ghi giá trị `v` dù khóa chưa có hay đã có; nếu đã có thì thay giá trị cũ. |
| `putIfAbsent(k, v)` | Chỉ đặt giá trị khi không có ánh xạ, hoặc khóa đang ánh xạ tới `null` theo hợp đồng mặc định của `Map`. |
| `replace(k, v)` | Chỉ thay nếu khóa đã có ánh xạ; không tạo entry khi khóa chưa tồn tại. |

Tệp **`MapUpdateVariantsDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class MapUpdateVariantsDemo {
    public static void main(String[] args) {
        Map<String, String> map = new HashMap<>();

        System.out.println(map.putIfAbsent("A", "First"));
        System.out.println(map.putIfAbsent("A", "Second"));
        System.out.println(map.get("A"));

        System.out.println(map.replace("B", "Ignored"));
        System.out.println(map.containsKey("B"));

        System.out.println(map.replace("A", "Updated"));
        System.out.println(map.get("A"));

        map.put("C", null);
        System.out.println(map.containsKey("C"));
        System.out.println(map.putIfAbsent("C", "Filled"));
        System.out.println(map.get("C"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac MapUpdateVariantsDemo.java
java MapUpdateVariantsDemo
~~~

Kết quả chính xác:

~~~text
null
First
First
null
false
First
Updated
true
null
Filled
~~~

Phép `putIfAbsent("A", "Second")` không thay `"First"` đã tồn tại. Phép `replace("B", "Ignored")` không tạo khóa `"B"`. Trong `HashMap`, khi `"C"` hiện đã tồn tại với value `null`, `putIfAbsent("C", "Filled")` vẫn có thể ghi `"Filled"`, còn `put("C", "Filled")` luôn thực hiện ghi bất kể value cũ. Đọc hợp đồng cụ thể của phương thức khi cần phân biệt cập nhật vô điều kiện, chỉ-thêm, chỉ-thay hoặc cập nhật nguyên tử trong môi trường đồng thời.

## 6. Đảm bảo khóa có `equals` và `hashCode` phù hợp

Nếu dùng đối tượng tự định nghĩa làm key, cần xác định chính xác các trường biểu diễn danh tính **logic** của khóa. Ví dụ hai `InvoiceKey` có cùng `invoiceNumber` được xem là cùng khóa trong ứng dụng; chúng phải bằng nhau theo `equals`, đồng thời có cùng `hashCode`.

Tệp **`InvoiceKeyDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class InvoiceKeyDemo {
    static final class InvoiceKey {
        private final String invoiceNumber;

        InvoiceKey(String invoiceNumber) {
            this.invoiceNumber = Objects.requireNonNull(invoiceNumber);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof InvoiceKey that)) {
                return false;
            }
            return invoiceNumber.equals(that.invoiceNumber);
        }

        @Override
        public int hashCode() {
            return invoiceNumber.hashCode();
        }
    }

    public static void main(String[] args) {
        Map<InvoiceKey, Integer> totals = new HashMap<>();
        InvoiceKey original = new InvoiceKey("INV-01");
        InvoiceKey duplicate = new InvoiceKey("INV-01");

        System.out.println(original == duplicate);
        System.out.println(original.equals(duplicate));
        System.out.println(totals.put(original, 100));
        System.out.println(totals.put(duplicate, 250));
        System.out.println(totals.size());
        System.out.println(totals.get(original));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac InvoiceKeyDemo.java
java InvoiceKeyDemo
~~~

Kết quả chính xác:

~~~text
false
true
null
100
1
250
~~~

Các quy tắc cần bảo toàn:

- **Tính nhất quán `equals`/`hashCode`:** nếu hai khóa bằng nhau theo `equals` thì bắt buộc cho cùng hash. Override `equals` nhưng quên `hashCode` có thể khiến `HashMap` không tìm thấy entry cần thay khi nhận một instance khóa khác nhưng bằng giá trị.
- **Tính ổn định của key:** tránh sửa dữ liệu tham gia `equals`/`hashCode` sau khi đưa khóa vào `HashMap`. Nếu mã băm thay đổi, thao tác `get`, `put`, `remove` bằng khóa đã biến đổi có thể cho kết quả ngoài dự kiến. Lớp `InvoiceKey` dùng trường `final` với `String` bất biến để tránh vấn đề này.
- **Tính đúng của mô hình nghiệp vụ:** không mặc định rằng mọi trường đều phải tham gia `equals`. Ví dụ trong `InvoiceKey`, `invoiceNumber` được định nghĩa làm khóa; nếu nghiệp vụ thực tế cần cả mã doanh nghiệp và số hóa đơn, phải đưa cả hai vào `equals` **và** `hashCode`.
- **Không suy luận giá trị được ghi đè từ tham chiếu khóa:** hai `InvoiceKey` là hai instance khác nhau, nhưng map chỉ giữ **một entry** vì cùng giá trị khóa.

Trong hiện thực `HashMap` thông thường, cập nhật bằng key tương đương sẽ sửa value của entry đã lưu thay vì thay hẳn đối tượng key đang nằm trong entry. Tuy nhiên, **đừng xây dựng logic ứng dụng trên việc instance key vật lý nào được giữ lại**: quy tắc mà giao diện `Map` bảo đảm là quan hệ ánh xạ key→value, không phải sự tồn tại của một object key gốc cụ thể. Đặc biệt, các map đặc biệt có thể định nghĩa cách so khóa khác `HashMap`.

## 7. Các trường hợp đặc biệt và sai lầm dễ gặp

### 7.1. Hai value bằng nhau không đồng nghĩa hai key bằng nhau

~~~java
Map<String, Integer> counts = new HashMap<>();
counts.put("A", 1);
counts.put("B", 1);
System.out.println(counts.size()); // 2
~~~

Hai entry có thể có **cùng value** mà vẫn là hai entry riêng vì **khóa khác nhau**. Map không phải tập hợp giá trị duy nhất.

### 7.2. Key có cùng hash code vẫn chưa phải khóa trùng

~~~java
Map<String, Integer> counts = new HashMap<>();
counts.put("Aa", 1);
counts.put("BB", 2);
System.out.println(counts.size()); // 2
~~~

`"Aa"` và `"BB"` trùng `hashCode` nhưng khác `equals`. Đây là collision hợp lệ; `HashMap` vẫn giữ cả hai.

### 7.3. Đừng dựa vào thứ tự in `HashMap` để kiểm tra thay thế

`HashMap` **không bảo đảm thứ tự duyệt key/entry**. Khi kiểm chứng, hãy gọi `size()`, `get(key)`, `containsKey(key)` hoặc kiểm tra giá trị trả về của `put`, thay vì suy luận từ chuỗi in ra của toàn bộ map.

Nếu cần thứ tự duyệt có bảo đảm, phải chọn cấu trúc đáp ứng yêu cầu khác, chẳng hạn `LinkedHashMap` (theo thứ tự chèn ở chế độ mặc định). Dù vậy, vấn đề chính của bài này vẫn là **khi nào value của một key bị thay thế**, không phải thứ tự duyệt.

### 7.4. Đừng mặc định mọi `Map` sử dụng cùng quy tắc “khóa trùng”

`HashMap` dựa trên `equals` và `hashCode` của key (với xử lý đặc biệt phù hợp cho `null`). Nhưng:

- `TreeMap` phân biệt khóa dựa trên kết quả **so sánh thứ tự** của `Comparator` được cung cấp hoặc `Comparable`. Hai key có thể được coi là tương đương khi `compare(k1, k2) == 0`.
- `IdentityHashMap` chủ ý dùng **danh tính tham chiếu** (`==`) thay cho `equals`, phục vụ các tình huống đặc biệt.
- `Map.of` là map không sửa được; gọi `put` thất bại với `UnsupportedOperationException`, còn trùng khóa trong đối số khi tạo map sẽ bị từ chối.

Vì vậy, luôn xem **loại map cụ thể** trước khi đưa ra giả định về tính tương đương của key và khả năng sửa đổi.

### 7.5. Đừng dùng `get(k) == null` để xác định khóa chưa tồn tại

Với `HashMap`, giá trị `null` là hợp lệ. `get(k) == null` có thể có nghĩa khóa chưa tồn tại **hoặc** đang ánh xạ tới `null`. Khi cần xác định có key thật hay không, dùng `containsKey(k)`. Tương tự, `put(k, v)` trả `null` có thể là thêm mới hoặc thay giá trị cũ `null`.

### 7.6. Đừng xem `put` trên `HashMap` thường là thao tác cập nhật an toàn trong đa luồng

`HashMap` không được thiết kế để nhiều luồng đồng thời sửa không có phối hợp. Mẫu **đọc rồi ghi** (`containsKey`/ `get` sau đó `put`) cũng không phải thao tác nguyên tử. Trong bài toán đồng thời, cần cấu trúc dữ liệu và thao tác thích hợp, ví dụ `ConcurrentHashMap` cùng `putIfAbsent`, `compute`, `merge` khi phù hợp; lưu ý `ConcurrentHashMap` không cho key/value `null` và ngữ nghĩa của các thao tác là khác nhau.

## 8. Checklist khi dùng `Map.put()`

1. **Xác định loại map:** `HashMap`, `TreeMap`, `IdentityHashMap`, map bất biến hay map đồng thời có quy tắc tương đương khóa và khả năng cập nhật khác nhau.
2. **Xác định thế nào là cùng khóa logic:** với `HashMap`, kiểm tra `equals`/`hashCode` của class key và bảo đảm trạng thái khóa ổn định.
3. **Dự đoán hành vi:** key mới thì thêm entry; key tương đương đã có thì thay value và giữ nguyên kích thước.
4. **Đọc kết quả trả về đúng nghĩa:** `put` trả old value; `null` có thể không rõ đã có key trước đó hay chưa nếu map cho giá trị `null`.
5. **Tách collision khỏi trùng khóa:** hash bằng nhau không đủ; phải xét quan hệ bằng nhau của key.
6. **Chọn đúng biến thể cập nhật:** dùng `putIfAbsent` khi chỉ muốn gán lúc absent/`null`, `replace` khi chỉ muốn thay key hiện có, hoặc các thao tác nguyên tử thích hợp khi có nhiều luồng.

## 9. Tự kiểm tra

1. Sau `map.put("A", 1); map.put("A", 2);`, `map.size()` và `map.get("A")` bằng bao nhiêu? Lần gọi `put` thứ hai trả gì?
2. Nếu gọi `map.put(new String("A"), 3)` trên map chứa `"A" → 2`, đây có phải khóa mới không? Vì sao?
3. Hai key có cùng `hashCode` nhưng `equals` trả `false`. Nếu dùng `HashMap`, lời gọi `put` sau có bắt buộc ghi đè giá trị của key trước không?
4. Vì sao `put("A", "ready")` trả `null` không đủ để kết luận `"A"` chưa tồn tại trước đó?
5. Điều gì có thể xảy ra nếu một key bị thay đổi trường dùng trong `hashCode` sau khi đã thêm vào `HashMap`?
6. Trong tình huống nào `putIfAbsent` phù hợp hơn `put`? Nếu khóa tồn tại nhưng value hiện là `null`, `putIfAbsent` của `HashMap` làm gì?

**Ghi nhớ:** Với `HashMap`, `Map.put(k, v)` **thêm entry nếu khóa mới**, nhưng **thay giá trị nếu đã có khóa tương đương theo `equals`/`hashCode`**, kể cả khi dùng một đối tượng khóa khác có cùng giá trị. `put` trả về value cũ (có thể `null`), còn **trùng hash code không tự động là trùng khóa**.