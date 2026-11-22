# Giảm vòng lặp lồng bằng Set hoặc chỉ mục Map

## 1. Nhận ra công việc tìm kiếm đang bị lặp lại

Giả sử có `n` đơn hàng và `m` khách hàng. Để tìm khách hàng của từng đơn hàng, cách trực tiếp là duyệt từng đơn hàng, rồi quét danh sách khách hàng đến khi tìm thấy mã khớp. Vấn đề không nằm ở hình thức “hai vòng `for`”, mà ở việc **cùng một tập dữ liệu bị tìm lại nhiều lần theo cùng điều kiện**.

Ý tưởng tối ưu là làm công việc chuẩn bị một lần:

```text
Cách quét lặp:
  mỗi phần tử bên trái -> quét dữ liệu bên phải -> lấy kết quả

Cách dùng chỉ mục:
  dữ liệu bên phải -> xây Set/Map một lần
  mỗi phần tử bên trái -> tra theo khóa -> lấy kết quả
```

Chỉ mục trong bài là một cấu trúc Java trong bộ nhớ, không phải chỉ mục cơ sở dữ liệu. Nó tổ chức lại cách tìm dữ liệu đã có trong chương trình.

Chọn cấu trúc dựa trên câu hỏi của vòng lặp bên trong:

| Cần trả lời | Cấu trúc thường phù hợp |
| --- | --- |
| Có ít nhất một phần tử mang khóa này không? | `Set<K>` |
| Bản ghi duy nhất theo khóa là gì? | `Map<K, V>` |
| Tất cả bản ghi có cùng khóa là gì? | `Map<K, List<V>>` |
| Có bao nhiêu bản ghi mang khóa này? | `Map<K, Long>` hoặc một kiểu đếm phù hợp |

Không đổi sang Map chỉ để làm mã ngắn hơn. Trước hết phải xác định khóa, quan hệ bằng nhau, số lượng kết quả và thứ tự cần giữ.

## 2. Phân tích chi phí trước và sau

### 2.1. Quét lặp

Với mỗi phần tử trong `n` phần tử bên trái, nếu cần kiểm tra tối đa `m` phần tử bên phải, số lượt kiểm tra có thể lên tới `n × m`. Khi `n` và `m` cùng tăng theo quy mô dữ liệu, đó là kiểu tăng trưởng bậc hai.

`break` sau khi thấy bản ghi đầu tiên có thể làm ít công việc hơn trên một số đầu vào, nhưng trường hợp không tìm thấy hoặc tìm thấy muộn vẫn phải quét nhiều. Ví dụ `n = 100.000`, `m = 50.000` cho giới hạn 5.000.000.000 cặp kiểm tra ở cách quét toàn bộ. Đây là số cặp lý thuyết, không phải thời gian chạy đã đo.

### 2.2. Xây chỉ mục rồi tra cứu

Với bảng băm có khóa phân bố phù hợp và coi chi phí tính mã băm/so sánh khóa là hằng số:

- Xây chỉ mục từ `m` phần tử: chi phí kỳ vọng O(m).
- Tra cứu cho `n` phần tử: chi phí kỳ vọng O(n).
- Tổng: **O(m + n)** cho kiểm tra tồn tại hoặc tra một bản ghi, cộng chi phí tạo đầu ra.
- Bộ nhớ phụ: O(u + c), với `u` là số khóa khác nhau và `c` là dung lượng bảng băm; constructor từ `Collection` như `new HashSet<>(allowed)` có thể dự trữ O(m) theo số phần tử nguồn, kể cả khi có nhiều phần tử trùng.

Đây là đánh đổi bộ nhớ để tránh tìm kiếm lặp. Không gọi `HashMap` hay `HashSet` là O(1) tuyệt đối với mọi khóa và mọi trường hợp. Tài liệu nêu điều kiện về sự phân bố mã băm; bản thân `hashCode` và `equals` cũng có thể đắt nếu khóa lớn hoặc thiết kế kém. [Tài liệu `HashMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HashMap.html).

### 2.3. Nếu phải tạo nhiều kết quả

Gọi `r` là số dòng kết quả phải phát ra trong phép ghép một–nhiều hoặc nhiều–nhiều. Xây chỉ mục nhóm rồi duyệt các nhóm phù hợp có chi phí kỳ vọng **O(m + n + r)**, không phải luôn O(m + n).

Nếu mọi phần tử bên trái đều khớp mọi phần tử bên phải và yêu cầu xuất toàn bộ cặp, `r = n × m`. Không cấu trúc tra cứu nào làm biến mất chi phí tạo những kết quả mà yêu cầu bài toán thực sự cần. Lợi ích của chỉ mục là tránh kiểm tra các cặp không liên quan.

## 3. Mẫu Set: chỉ cần biết có tồn tại

Giả sử cần giữ những mã yêu cầu có trong một danh sách được phép. Vòng lặp quét có `break` khi gặp lần khớp đầu tiên; kết quả phải giữ thứ tự và số lần xuất hiện của danh sách yêu cầu.

Cách thay đổi:

1. Tạo `HashSet` từ danh sách được phép **trước vòng lặp bên ngoài**.
2. Tiếp tục duyệt danh sách yêu cầu theo thứ tự cũ.
3. Với mỗi mã, gọi `contains`; nếu có thì thêm chính phần tử đang duyệt vào danh sách kết quả.

Set loại phần tử trùng trong phía tra cứu, điều đó không làm mất bản sao ở phía yêu cầu vì ta vẫn duyệt danh sách yêu cầu. Ngược lại, nếu chuyển luôn kết quả sang Set, ta đã đổi hợp đồng đầu ra.

Ví dụ:

```text
yêu cầu:    [A, C, A, null, B]
được phép:  [B, A, null]
kết quả:    [A, A, null, B]
```

`HashSet` cho phép phần tử `null` và không bảo đảm thứ tự duyệt. Trong mẫu này không duyệt Set để xuất kết quả, nên thứ tự của Set không quyết định thứ tự đầu ra. [Tài liệu `HashSet`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HashSet.html).

### Khi Set làm thay đổi bài toán

Nếu cần kiểm tra số lần xuất hiện, Set không đủ. Ví dụ bên phải có hai mã `A`, bên trái có ba mã `A`, và mỗi mã bên phải chỉ được sử dụng một lần: kiểm tra `contains` sẽ nhận cả ba, trái với yêu cầu ghép theo số lượng.

Trong trường hợp đó, có thể cần Map đếm số lượng còn lại rồi giảm sau mỗi lần ghép. Nếu cần giữ toàn bộ bản ghi tương ứng, cần Map chứa danh sách chứ không chỉ Set các khóa.

## 4. Mẫu Map: lấy một bản ghi theo khóa

Đối với đơn hàng và khách hàng, khóa tự nhiên có thể là mã khách hàng:

```text
customers -> Map<customerId, Customer>
orders    -> tra customerId -> lấy Customer
```

### 4.1. Khóa trùng phải có chính sách rõ

Một Map chỉ giữ tối đa một giá trị cho mỗi khóa. Nếu hai bản ghi có cùng mã, cách xây Map phải phản ánh đúng hợp đồng dữ liệu:

| Hợp đồng | Cách xây chỉ mục khi giá trị luôn khác `null` | Ý nghĩa |
| --- | --- | --- |
| Khóa phải duy nhất | Phát hiện trùng và báo lỗi | Dữ liệu trùng là đầu vào không hợp lệ |
| Giữ bản ghi đầu tiên | `putIfAbsent` | Tương ứng quét theo thứ tự rồi `break` ở lần khớp đầu |
| Giữ bản ghi cuối cùng | `put` theo thứ tự nguồn | Bản ghi sau thay bản ghi trước |
| Cần tất cả bản ghi | `Map<K, List<V>>` | Giữ số lượng và thứ tự trong từng nhóm |

Không dùng `put` ghi đè rồi coi đó là tối ưu bảo toàn hành vi của vòng quét lấy bản ghi đầu tiên. Nếu dữ liệu trùng được phép, phải chọn đúng chính sách đầu tiên/cuối cùng thay vì tự thêm quy tắc loại bỏ hoặc báo lỗi.

`Collectors.toMap(keyMapper, valueMapper)` cũng không tự giải quyết mọi hợp đồng: overload không có hàm gộp sẽ báo lỗi khi khóa trùng. Khi dùng overload có hàm gộp, hàm đó phải mang ý nghĩa nghiệp vụ rõ ràng. [Tài liệu `Collectors`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collectors.html).

### 4.2. Không tìm thấy khác với giá trị `null`

`HashMap.get(key)` có thể trả `null` khi không có khóa, hoặc khi khóa được ánh xạ tới giá trị `null`. Nếu cho phép giá trị `null`, chỉ nhìn kết quả `get` không phân biệt được hai trường hợp; có thể cần `containsKey` hoặc thiết kế lại biểu diễn dữ liệu thiếu.

Ví dụ trong chương trình bên dưới quy định giá trị `Customer` của chỉ mục luôn khác `null`. Vì vậy `get(...) == null` được dùng để biểu diễn không tìm thấy. Quy định này thuộc ví dụ, không phải tính chất chung của mọi `Map`.

### 4.3. Giữ đầu ra của phép ghép

Nếu cần giữ mọi đơn hàng, kể cả đơn không tìm thấy khách hàng, hãy luôn phát một dòng cho mỗi đơn hàng và xử lý giá trị thiếu. Nếu chỉ cần các đơn có khách hàng, mới bỏ qua dòng không khớp.

Đó là khác biệt giữa phép ghép giữ toàn bộ phía trái (left join) và phép ghép chỉ giữ dòng khớp (inner join). Tối ưu tra cứu không được tự đổi loại phép ghép.

## 5. Mẫu Map chứa List: lấy tất cả bản ghi khớp

Giả sử một đơn hàng có nhiều dòng hàng. Chỉ mục `Map<orderId, Line>` sẽ làm mất dữ liệu nếu ghi đè. Dùng:

```java
Map<String, List<Line>> byOrder = new HashMap<>();
for (Line line : lines) {
    byOrder.computeIfAbsent(line.orderId(), key -> new ArrayList<>()).add(line);
}
```

Đoạn này cần có kiểu `Line` và các import; chương trình đầy đủ ở phần sau cung cấp chúng. `computeIfAbsent` tạo danh sách khi chưa có giá trị cho khóa, sau đó thêm dòng vào nhóm. Không thay đổi chính Map bên trong hàm tạo danh sách. [Tài liệu `Map.computeIfAbsent`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html#computeIfAbsent(K,java.util.function.Function)).

Khi duyệt đơn hàng:

```java
for (Order order : orders) {
    for (Line line : byOrder.getOrDefault(order.id(), List.of())) {
        result.add(order.id() + ":" + line.sku());
    }
}
```

Mã vẫn có hai vòng lặp lồng về hình thức. Khác biệt là vòng trong chỉ duyệt các dòng thuộc đúng đơn hàng, không quét toàn bộ `lines` mỗi lần. Đừng đánh giá thuật toán chỉ bằng số vòng lặp nhìn thấy.

Nếu xây nhóm theo thứ tự `lines`, mỗi List trong nhóm giữ thứ tự tương ứng. Nếu tiếp tục duyệt `orders` theo thứ tự cũ, đầu ra giữ thứ tự của vòng quét ban đầu: đơn hàng trước, rồi các dòng khớp theo thứ tự nguồn.

Nếu `orders` lặp lại cùng mã, nhóm được phát lại cho từng lần xuất hiện, giống vòng lặp lồng đầy đủ. Nếu hai dòng hàng trùng nội dung, List vẫn giữ cả hai. Không dùng Set làm giá trị nhóm nếu yêu cầu là bảo toàn số lần xuất hiện.

## 6. Chương trình Java 17+ đầy đủ: so sánh ba mẫu

Lưu mã sau thành `IndexDemo.java`. Dữ liệu khách hàng trong phép ghép hợp lệ có mã duy nhất; `uniqueCustomers` còn minh họa cách từ chối dữ liệu vi phạm quy định đó. Bản lọc bằng Set chủ động hỗ trợ `null` bằng cách chọn `HashSet` và dùng cùng ngữ nghĩa `Objects.equals` ở bản quét.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class IndexDemo {
    record Customer(String id, String name) {
        Customer {
            Objects.requireNonNull(id);
            Objects.requireNonNull(name);
        }
    }

    record Order(String id, String customerId) {}
    record Line(String orderId, String sku) {}

    static List<String> filterNested(List<String> wanted, List<String> allowed) {
        List<String> result = new ArrayList<>();
        for (String value : wanted) {
            for (String candidate : allowed) {
                if (Objects.equals(value, candidate)) {
                    result.add(value);
                    break;
                }
            }
        }
        return result;
    }

    static List<String> filterIndexed(List<String> wanted, List<String> allowed) {
        Set<String> allowedIndex = new HashSet<>(allowed);
        List<String> result = new ArrayList<>();
        for (String value : wanted) {
            if (allowedIndex.contains(value)) {
                result.add(value);
            }
        }
        return result;
    }

    static Map<String, Customer> uniqueCustomers(List<Customer> customers) {
        Map<String, Customer> index = new HashMap<>();
        for (Customer customer : customers) {
            Customer previous = index.putIfAbsent(customer.id(), customer);
            if (previous != null) {
                throw new IllegalArgumentException("duplicate customer: " + customer.id());
            }
        }
        return index;
    }

    static List<String> customerJoinNested(List<Order> orders, List<Customer> customers) {
        List<String> result = new ArrayList<>();
        for (Order order : orders) {
            String name = "UNKNOWN";
            for (Customer customer : customers) {
                if (Objects.equals(order.customerId(), customer.id())) {
                    name = customer.name();
                    break;
                }
            }
            result.add(order.id() + "->" + name);
        }
        return result;
    }

    static List<String> customerJoinIndexed(List<Order> orders, List<Customer> customers) {
        Map<String, Customer> byId = uniqueCustomers(customers);
        List<String> result = new ArrayList<>();
        for (Order order : orders) {
            Customer customer = byId.get(order.customerId());
            String name = customer == null ? "UNKNOWN" : customer.name();
            result.add(order.id() + "->" + name);
        }
        return result;
    }

    static List<String> allLinesNested(List<Order> orders, List<Line> lines) {
        List<String> result = new ArrayList<>();
        for (Order order : orders) {
            for (Line line : lines) {
                if (Objects.equals(order.id(), line.orderId())) {
                    result.add(order.id() + ":" + line.sku());
                }
            }
        }
        return result;
    }

    static List<String> allLinesIndexed(List<Order> orders, List<Line> lines) {
        Map<String, List<Line>> byOrder = new HashMap<>();
        for (Line line : lines) {
            byOrder.computeIfAbsent(line.orderId(), key -> new ArrayList<>()).add(line);
        }
        List<String> result = new ArrayList<>();
        for (Order order : orders) {
            for (Line line : byOrder.getOrDefault(order.id(), List.of())) {
                result.add(order.id() + ":" + line.sku());
            }
        }
        return result;
    }

    public static void main(String[] args) {
        List<String> wanted = Arrays.asList("A", "C", "A", null, "B");
        List<String> allowed = Arrays.asList("B", "A", null);
        List<String> filtered = filterIndexed(wanted, allowed);
        System.out.println("membership=" + filtered);
        System.out.println("membership same=" + filtered.equals(filterNested(wanted, allowed)));

        List<Customer> customers = List.of(
                new Customer("c1", "Lan"),
                new Customer("c2", "Minh"));
        List<Order> orders = List.of(
                new Order("o2", "c2"),
                new Order("o1", "c1"),
                new Order("o9", "missing"));

        List<String> names = customerJoinIndexed(orders, customers);
        System.out.println("customer join=" + names);
        System.out.println("customer join same=" + names.equals(customerJoinNested(orders, customers)));

        List<Line> lines = List.of(
                new Line("o1", "pen"),
                new Line("o2", "book"),
                new Line("o1", "ink"),
                new Line("o1", "pen"));
        List<String> allLines = allLinesIndexed(orders, lines);
        System.out.println("line join=" + allLines);
        System.out.println("line join same=" + allLines.equals(allLinesNested(orders, lines)));

        try {
            uniqueCustomers(List.of(
                    new Customer("c1", "Lan"),
                    new Customer("c1", "Other")));
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 IndexDemo.java
java IndexDemo
```

Stdout chính xác:

```text
membership=[A, A, null, B]
membership same=true
customer join=[o2->Minh, o1->Lan, o9->UNKNOWN]
customer join same=true
line join=[o2:book, o1:pen, o1:ink, o1:pen]
line join same=true
duplicate customer: c1
```

### Đọc bằng chứng trong chương trình

- `filterNested` và `filterIndexed` trả cùng List, gồm hai lần `A`, một `null` và thứ tự của `wanted`.
- Hai phép ghép khách hàng có cùng kết quả trên dữ liệu đáp ứng điều kiện mã duy nhất. Đơn `o9` vẫn được giữ với nhãn `UNKNOWN`.
- Hai phép ghép dòng hàng giữ cả hai dòng `o1:pen`; bản có chỉ mục không làm mất bản sao.
- Không in chính `HashMap`, nên stdout không phụ thuộc thứ tự duyệt Map.
- Trường hợp mã khách hàng trùng bị `uniqueCustomers` từ chối. Đây là kiểm tra điều kiện đầu vào đã công bố. Bản quét lấy lần đầu không có kiểm tra đó, nên không được nói hai hàm có cùng hành vi với mọi đầu vào bất kỳ.

Nếu phải bảo toàn hành vi lấy bản ghi đầu tiên ngay cả khi mã trùng được phép, thay phần xây chỉ mục khách hàng bằng vòng lặp dùng `putIfAbsent` và **không ném lỗi khi đã có giá trị**. Điều này đúng trong ví dụ vì mọi giá trị `Customer` đưa vào Map đều khác `null`. Nếu cần giữ mọi khách hàng trùng mã, phải đổi kiểu chỉ mục sang List theo khóa.

Chương trình xác nhận kết quả trên đầu vào mẫu, không đo tốc độ và không chứng minh mọi điều kiện biên. Khi áp dụng thật, phải kiểm tra các hợp đồng của dữ liệu riêng.

## 7. Thiết kế khóa để chỉ mục trả đúng dữ liệu

### 7.1. Quan hệ so sánh phải tương đương với bản quét

Nếu vòng cũ so bằng `customer.id().equals(...)`, chỉ mục theo `id` có thể phù hợp. Nếu vòng cũ so không phân biệt hoa/thường hoặc có chuẩn hóa khoảng trắng, dùng chuỗi thô làm khóa sẽ đổi quan hệ khớp.

Chỉ chuẩn hóa theo quy tắc nghiệp vụ đã xác định và áp dụng cùng quy tắc cho cả khi xây lẫn khi tra. Không tự `trim()` hoặc đổi hoa/thường cho mã vốn phân biệt các ký tự đó. Với so sánh đặc biệt như quan hệ theo comparator hoặc danh tính đối tượng, phải kiểm tra lại vì một `HashSet` thông thường dựa trên `equals` không nhất thiết tương đương.

### 7.2. Khóa tổng hợp nên có cấu trúc rõ

Nếu điều kiện khớp gồm mã cửa hàng và mã sản phẩm, có thể dùng record:

```java
record ProductKey(String shopId, String sku) {}

// Minh họa trong phương thức đã có các biến tương ứng:
Map<ProductKey, Product> byKey = new HashMap<>();
byKey.put(new ProductKey(product.shopId(), product.sku()), product);
Product found = byKey.get(new ProductKey(shopId, sku));
```

Đoạn này minh họa thiết kế, không phải chương trình độc lập: kiểu `Product` và các biến phải được cung cấp bởi ứng dụng. Không ghép khóa bằng phép nối chuỗi thiếu quy tắc rõ; chẳng hạn ghép trực tiếp hai thành phần có thể khiến các cặp khác nhau ra cùng chuỗi.

Record có trường chuỗi phù hợp cho ví dụ vì quan hệ bằng nhau dựa trên các thành phần ổn định. Một record chứa thành phần có thể thay đổi nội dung vẫn cần được xem xét cẩn thận; tính bất biến của biến tham chiếu không tự biến toàn bộ đồ thị dữ liệu thành bất biến.

### 7.3. Tôn trọng `equals` và `hashCode`

Các đối tượng bằng nhau theo `equals` phải có cùng mã băm. Ngược lại, cùng mã băm chưa chứng minh bằng nhau. Dùng lớp khóa tùy biến nhưng chỉ override `equals` mà bỏ qua `hashCode` có thể khiến chỉ mục không tìm được dữ liệu như dự kiến. [Hợp đồng `Object.hashCode`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html#hashCode()).

Không sửa các trường tham gia so sánh/mã băm khi đối tượng đang làm khóa trong Map hoặc phần tử của Set băm. Chọn một khóa ổn định tách khỏi đối tượng nghiệp vụ có thể thay đổi thường dễ quản lý hơn. Tài liệu Map cũng cảnh báo hành vi khi thay đổi khóa làm ảnh hưởng quan hệ bằng nhau. [Tài liệu `Map`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html).

## 8. Thứ tự và thời gian sống của chỉ mục

### 8.1. Thứ tự kết quả đến từ đâu?

Nếu Map chỉ dùng để `get`, còn đầu ra được tạo khi duyệt List nguồn, thứ tự đầu ra đến từ List đó. Không cần `LinkedHashMap` chỉ vì muốn giữ thứ tự của đơn hàng trong mẫu này.

Nếu sau đó phải duyệt chính các nhóm theo thứ tự khóa xuất hiện lần đầu, `LinkedHashMap` ở chế độ thứ tự chèn có thể phù hợp. Nếu cần sắp xếp khóa, đó lại là yêu cầu khác. [Tài liệu `LinkedHashMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html).

### 8.2. Xây một lần ở đúng phạm vi

Ví dụ sai về mặt tối ưu:

```java
for (String value : wanted) {
    Set<String> index = new HashSet<>(allowed);
    if (index.contains(value)) {
        result.add(value);
    }
}
```

Mỗi vòng lại xây cùng chỉ mục nên vẫn làm khoảng O(n × m) công việc xây dựng, còn phát sinh nhiều cấp phát hơn. Đưa việc xây chỉ mục ra ngoài vòng cần tra cứu.

Nếu cùng dữ liệu được dùng cho nhiều batch, tái sử dụng chỉ mục có thể phân bổ chi phí xây dựng qua nhiều lần tra. Nhưng khi dữ liệu nguồn thay đổi, một chỉ mục được tạo trước đó không tự cập nhật cấu trúc theo List nguồn.

Map thường giữ tham chiếu tới đối tượng dữ liệu chứ không sao chép sâu. Vì thế thay đổi trường giá trị có thể nhìn thấy qua tham chiếu, trong khi việc thêm/xóa bản ghi hoặc đổi khóa không tự duy trì chỉ mục đúng. Cần quy định xây lại, cập nhật đồng bộ hoặc dùng một phiên bản dữ liệu nhất quán cho cả phép xử lý. Không đưa chỉ mục cục bộ thành cache toàn cục chỉ để tránh vài lần xây dựng mà chưa xử lý tính mới và thời gian sống dữ liệu.

Nếu có nhiều luồng cập nhật, tính an toàn của cả dữ liệu nguồn và chỉ mục là một yêu cầu riêng. Đổi sang một Map đồng thời không tự làm chuỗi “đọc nguồn → xây → tra” trở thành một ảnh chụp nhất quán.

## 9. Khi nào chỉ mục không đáng xây hoặc chưa đủ?

| Tình huống | Hướng đánh giá |
| --- | --- |
| Chỉ tra một lần trên tập rất nhỏ | Quét trực tiếp có thể đơn giản hơn và tránh bộ nhớ phụ |
| Tra rất nhiều lần trên cùng tập lớn | Chi phí xây chỉ mục có cơ hội được phân bổ tốt |
| Bộ nhớ hạn chế | Tính cả bảng băm, nút, khóa mới và các List nhóm; không chỉ số phần tử |
| Điều kiện khớp là khoảng, tiền tố hoặc độ gần đúng | Bảng băm theo khóa bằng nhau không trực tiếp giải quyết toàn bộ; có thể cần phân nhóm, cấu trúc có thứ tự hoặc thuật toán khác |
| Mọi cặp đều phải được xử lý | Chi phí đầu ra hoặc công việc cặp vẫn có thể là O(n × m) |
| Khóa thay đổi liên tục | Tính cả chi phí duy trì chỉ mục và đồng bộ dữ liệu |

Một chỉ mục nhóm có thể giảm vùng tìm kiếm rồi vẫn cần kiểm tra điều kiện phụ trong nhóm. Khi đó phải cộng chi phí số ứng viên thực sự được duyệt; không công bố O(n + m) nếu các nhóm lớn vẫn bị quét lại nhiều lần.

## 10. Kiểm chứng tối ưu theo hai bước

### 10.1. Trước hết chứng minh kết quả

Đối chiếu bản quét và bản có chỉ mục với những tình huống phù hợp hợp đồng:

- Một hoặc cả hai tập rỗng.
- Không có phần tử khớp; tất cả đều khớp; phần tử khớp đầu/cuối.
- Phần tử trùng ở phía tra cứu và phía phát kết quả.
- Khóa trùng: duy nhất, giữ đầu, giữ cuối hay giữ tất cả theo quy định đã chọn.
- `null`, giá trị thiếu, khóa tổng hợp và quy tắc chuẩn hóa nếu có hỗ trợ.
- Thứ tự List kết quả và số lượng bản sao; không chỉ so một Set của các kết quả.

Trong mã có hiệu ứng phụ hoặc hàm so sánh không thuần, thay cách tra còn có thể thay số lần gọi, thứ tự gọi và thời điểm phát sinh lỗi. Không coi việc cùng tập kết quả là đủ nếu những hành vi đó thuộc hợp đồng ứng dụng.

### 10.2. Sau đó đo đúng phạm vi

Nếu chỉ mục được xây cho từng yêu cầu, đo cả xây chỉ mục và tạo đầu ra. Nếu chỉ mục đã tồn tại để phục vụ nhiều lần tra, có thể đo riêng phần tra nhưng phải công bố chi phí xây và duy trì ở đâu.

Thử nhiều quy mô `n`, `m`, tỷ lệ khớp và mức độ trùng khóa. Với phép ghép nhiều kết quả, ghi thêm `r`. Dùng JMH khi cần phép đo vi mô đáng tin và kiểm tra tải thật để xem thay đổi có cải thiện mục tiêu của ứng dụng hay không. Không dùng số phép tra cứu để suy thành số mili giây cố định.

## 11. Bài tập tự áp dụng

Một chương trình duyệt 200.000 giao dịch và, với mỗi giao dịch, quét 80.000 cấu hình để tìm cấu hình theo cặp `(merchantId, currency)`.

1. Xác định Set có đủ không, hay phải dùng Map theo khóa tổng hợp.
2. Làm rõ nếu có hai cấu hình cùng khóa: báo lỗi, giữ đầu, giữ cuối hay cần gộp?
3. Nêu cách giữ thứ tự giao dịch và cách xử lý không tìm thấy.
4. Viết công thức chi phí gồm xây chỉ mục, tra và đầu ra; ghi giả định về băm/so sánh khóa.
5. Nếu cấu hình đổi giữa lúc xử lý, quy định phiên bản dữ liệu hoặc cách cập nhật chỉ mục.

Một phương án đúng phải tránh tìm lại dữ liệu không cần thiết và đồng thời giữ nguyên hợp đồng về quan hệ khớp, thứ tự, số lần xuất hiện và dữ liệu thiếu.
