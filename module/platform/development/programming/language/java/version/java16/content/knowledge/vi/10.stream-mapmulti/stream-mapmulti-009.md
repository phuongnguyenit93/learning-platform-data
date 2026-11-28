# Làm phẳng collection lồng nhau và giữ thứ tự phát trong từng mapper

`Stream.mapMulti` có thể làm phẳng dữ liệu dạng collection lồng nhau bằng cách duyệt từng collection con và gọi `Consumer.accept` cho mỗi phần tử cần phát. Mỗi phần tử nguồn có thể đóng góp không, một hoặc nhiều phần tử vào Stream kết quả.

Khi xử lý collection lồng nhau, thứ tự rất quan trọng. Nếu Stream nguồn có encounter order và các collection con có thứ tự duyệt xác định, ta có thể giữ nguyên thứ tự đó bằng cách phát kết quả theo đúng thứ tự vòng lặp. `mapMulti` không tự sắp xếp hay đảo thứ tự các phần tử; thứ tự đầu ra phụ thuộc vào thứ tự phần tử nguồn, thứ tự duyệt collection con và thứ tự gọi `accept` trong mapper.

## 1. Cơ chế làm phẳng bằng Consumer

Giả sử Stream nguồn chứa các danh sách số nguyên. Mỗi danh sách là một phần tử nguồn; ta muốn nối các số trong tất cả danh sách thành một Stream duy nhất.

```java
import java.util.List;

List<List<Integer>> groups = List.of(
    List.of(3, 1),
    List.of(4, 2, 5),
    List.of()
);

List<Integer> flattened = groups.stream()
    .<Integer>mapMulti((group, emit) -> {
        for (Integer number : group) {
            emit.accept(number);
        }
    })
    .toList();
```

Kết quả:

```text
[3, 1, 4, 2, 5]
```

Mapper được gọi cho từng danh sách trong Stream nguồn. Vòng lặp duyệt các phần tử của danh sách hiện tại và phát từng số qua `emit.accept`.

- Danh sách thứ nhất phát `3`, rồi `1`.
- Danh sách thứ hai phát `4`, rồi `2`, rồi `5`.
- Danh sách rỗng không gọi `accept`, nên không đóng góp phần tử đầu ra.

Stream kết quả là phép nối các phần tử con theo thứ tự duyệt của từng danh sách, đồng thời theo encounter order của Stream nguồn.

## 2. Thứ tự gọi accept quyết định thứ tự trong một mapper

Trong một lần gọi mapper, các câu lệnh được thực thi theo thứ tự chương trình. Nếu gọi `accept` lần lượt với A, B rồi C, mapper phát A, B rồi C.

```java
import java.util.List;

List<String> values = List.of("first", "second");

List<String> expanded = values.stream()
    .<String>mapMulti((value, emit) -> {
        emit.accept(value + "-1");
        emit.accept(value + "-2");
        emit.accept(value + "-3");
    })
    .toList();
```

Kết quả:

```text
[
  first-1, first-2, first-3,
  second-1, second-2, second-3
]
```

Các kết quả được phát theo thứ tự gọi `accept` trong từng lần mapper. Mapper của phần tử nguồn tiếp theo tiếp tục đóng góp kết quả theo encounter order khi Stream có thứ tự.

Nếu thay đổi thứ tự gọi `accept`, thứ tự các phần tử đầu ra tương ứng cũng thay đổi. Vì vậy, vòng lặp và thứ tự duyệt collection con là phần quyết định trình tự dữ liệu được làm phẳng.

## 3. Làm phẳng danh sách dòng hàng trong đơn hàng

Trong ứng dụng thực tế, một đơn hàng có nhiều dòng hàng. Ta có thể chuyển danh sách đơn hàng thành danh sách dòng hàng mà vẫn giữ thứ tự các đơn và thứ tự dòng hàng bên trong từng đơn.

```java
import java.util.List;

record LineItem(String sku, int quantity) {}
record Order(String id, List<LineItem> items) {}

List<Order> orders = List.of(
    new Order("O-100", List.of(
        new LineItem("BOOK-01", 2),
        new LineItem("PEN-02", 1)
    )),
    new Order("O-101", List.of(
        new LineItem("BAG-03", 1),
        new LineItem("NOTE-04", 4)
    ))
);

List<LineItem> allItems = orders.stream()
    .<LineItem>mapMulti((order, emit) -> {
        for (LineItem item : order.items()) {
            emit.accept(item);
        }
    })
    .toList();
```

Kết quả theo thứ tự:

```text
BOOK-01, PEN-02, BAG-03, NOTE-04
```

Hai dòng hàng của đơn `O-100` đứng trước hai dòng hàng của `O-101`, vì Stream nguồn là Stream có encounter order từ một `List`. Trong mỗi đơn, các dòng hàng được phát theo thứ tự xuất hiện trong `order.items()`.

Cách viết này hữu ích khi cần biến dữ liệu cha-con thành một luồng phẳng để tiếp tục lọc, tính toán hoặc chuyển đổi.

## 4. Lọc phần tử con mà vẫn giữ thứ tự còn lại

Làm phẳng không có nghĩa phải phát mọi phần tử con. Mapper có thể kiểm tra điều kiện trước khi gọi Consumer. Những phần tử được giữ lại vẫn xuất hiện theo thứ tự duyệt ban đầu.

Ví dụ, chỉ lấy dòng hàng có số lượng dương:

Tiếp tục dùng kiểu `Order`, `LineItem` và danh sách `orders` đã khai báo ở mục 3:

```java
List<String> availableSkus = orders.stream()
    .<String>mapMulti((order, emit) -> {
        for (LineItem item : order.items()) {
            if (item.quantity() > 0) {
                emit.accept(item.sku());
            }
        }
    })
    .toList();
```

Mapper duyệt các dòng hàng theo thứ tự trong từng đơn. Dòng không hợp lệ không được phát; các dòng còn lại giữ nguyên thứ tự tương đối. Đây là tính chất thường được gọi là ổn định (stable) đối với việc lọc: loại bỏ một số phần tử không làm đảo vị trí tương đối của các phần tử còn lại.

Nếu muốn sắp xếp SKU, hãy thực hiện một thao tác sắp xếp riêng trong pipeline. `mapMulti` chỉ phát theo thứ tự đã duyệt, không tự sắp xếp.

## 5. Làm phẳng nhiều cấp collection bằng các vòng lặp lồng nhau

Dữ liệu có thể lồng nhiều hơn hai cấp. Ví dụ, một công ty có nhiều phòng ban, mỗi phòng ban có nhiều nhóm và mỗi nhóm có nhiều nhân viên. Có thể duyệt từng cấp trong cùng mapper:

```java
import java.util.List;

record Employee(String name) {}
record Team(String name, List<Employee> employees) {}
record Department(String name, List<Team> teams) {}

List<Department> departments = List.of(
    new Department("Engineering", List.of(
        new Team("Platform", List.of(
            new Employee("An"),
            new Employee("Binh")
        )),
        new Team("Mobile", List.of(
            new Employee("Chi")
        ))
    )),
    new Department("Support", List.of(
        new Team("Customer Care", List.of(
            new Employee("Dung")
        ))
    ))
);

List<String> employeeNames = departments.stream()
    .<String>mapMulti((department, emit) -> {
        for (Team team : department.teams()) {
            for (Employee employee : team.employees()) {
                emit.accept(employee.name());
            }
        }
    })
    .toList();
```

Kết quả:

```text
[An, Binh, Chi, Dung]
```

Thứ tự được tạo theo ba cấp:

1. Encounter order của các phòng ban trong Stream nguồn.
2. Thứ tự các nhóm trong danh sách của từng phòng ban.
3. Thứ tự nhân viên trong danh sách của từng nhóm.

Vòng lặp ngoài cùng hoàn tất các nhóm của một phòng ban trước khi chuyển sang phòng ban tiếp theo. Vì thế, danh sách kết quả phản ánh đúng thứ tự duyệt lồng nhau.

Nếu một cấp chứa collection rỗng, vòng lặp ở cấp đó không chạy và không phát phần tử. Điều này tự nhiên tương ứng với việc một nhánh nguồn đóng góp không phần tử đầu ra.

## 6. So sánh với flatMap

`flatMap` cũng có thể làm phẳng collection lồng nhau. Tiếp tục dùng `orders`, `Order` và `LineItem` ở mục 3; cách viết tương đương là:

```java
List<LineItem> allItems = orders.stream()
    .flatMap(order -> order.items().stream())
    .toList();
```

Dùng `mapMulti`:

```java
List<LineItem> allItems = orders.stream()
    .<LineItem>mapMulti((order, emit) -> {
        for (LineItem item : order.items()) {
            emit.accept(item);
        }
    })
    .toList();
```

Cả hai pipeline đều nối các dòng hàng của từng đơn vào một Stream kết quả. Với Stream có thứ tự và collection con có thứ tự duyệt xác định, cả hai cách đều giữ encounter order.

Khác biệt nằm ở cách biểu đạt:

- `flatMap` nhận một Stream con cho mỗi phần tử nguồn rồi làm phẳng các Stream con.
- `mapMulti` nhận Consumer và cho phép mapper phát từng phần tử trực tiếp.
- `mapMulti` thuận tiện khi việc duyệt collection con bằng vòng lặp, có điều kiện hoặc nhiều nhánh phát kết quả.
- `flatMap` tự nhiên khi dữ liệu con đã có dạng Stream và cần kết hợp các thao tác Stream trên dữ liệu con.

Không có quy tắc rằng `mapMulti` luôn nhanh hơn `flatMap`. API không cam kết mọi cách triển khai đều tránh buffer hoặc mọi workload đều có cùng đặc tính hiệu năng. Hãy chọn cách viết dễ hiểu và đo đạc nếu cần tối ưu.

## 7. Thứ tự của collection con phụ thuộc loại collection

`mapMulti` giữ thứ tự mà mapper phát ra. Tuy nhiên, mapper chỉ có thể duyệt theo thứ tự mà collection con cung cấp. Không phải mọi kiểu collection đều cam kết một encounter order ổn định.

| Collection | Đặc điểm thứ tự duyệt |
|---|---|
| `List` | Có thứ tự theo vị trí phần tử |
| `LinkedHashSet` | Giữ thứ tự chèn |
| `TreeSet` | Theo thứ tự của comparator hoặc thứ tự tự nhiên |
| `HashSet` | Không cam kết thứ tự duyệt |

Ví dụ, nếu mỗi nhóm lưu dữ liệu trong `HashSet`, không nên giả định phần tử sẽ được phát theo thứ tự thêm vào. `mapMulti` không tự khôi phục thứ tự chèn mà collection không cam kết.

`Map` không triển khai `Collection`, nhưng nếu làm phẳng các giá trị của Map bằng `map.values()`, thứ tự duyệt cũng phụ thuộc loại Map: `LinkedHashMap` giữ thứ tự chèn, `TreeMap` duyệt theo thứ tự khóa và `HashMap` không cam kết thứ tự.

Nếu thứ tự nghiệp vụ quan trọng, hãy chọn collection có thứ tự phù hợp hoặc sắp xếp dữ liệu trước khi phát. Với một `List`, thứ tự vị trí vốn đã rõ ràng nên vòng lặp for-each là đủ.

## 8. Encounter order của Stream nguồn

Ngoài thứ tự của collection con, cần xét thứ tự của Stream nguồn:

- `list.stream()` có encounter order theo thứ tự phần tử trong List.
- `Stream.of(a, b, c)` có encounter order theo thứ tự các đối số.
- Stream từ một nguồn không có thứ tự, chẳng hạn `HashSet`, không cung cấp thứ tự nghiệp vụ đáng tin cậy.
- Gọi `unordered()` cho phép pipeline bỏ ràng buộc encounter order, có thể hữu ích cho một số xử lý song song nhưng không phù hợp khi thứ tự là yêu cầu đầu ra.

Với Stream có encounter order, `mapMulti` là thao tác bảo toàn thứ tự: các nhóm kết quả gắn với phần tử nguồn được kết hợp theo encounter order của nguồn, còn trong mỗi nhóm kết quả được phát theo thứ tự gọi Consumer.

Ví dụ:

```java
List<List<String>> groups = List.of(
    List.of("A", "B"),
    List.of("C", "D")
);

List<String> result = groups.stream()
    .<String>mapMulti((group, emit) -> {
        group.forEach(emit);
    })
    .toList();
```

Kết quả là `[A, B, C, D]`. Nếu nguồn hoặc collection con không có thứ tự xác định, kết quả không thể được xem là có một thứ tự nghiệp vụ cố định.

## 9. Thứ tự khi dùng parallel Stream

Với Stream có encounter order, việc chuyển sang parallel không tự động xóa thứ tự kết quả. Mapper của các phần tử nguồn khác nhau có thể được thực thi đồng thời, nhưng pipeline có thứ tự vẫn duy trì encounter order của kết quả ở các thao tác có bảo toàn thứ tự, chẳng hạn `toList()`.

Ví dụ:

```java
List<List<Integer>> groups = List.of(
    List.of(1, 2),
    List.of(3, 4),
    List.of(5, 6)
);

List<Integer> result = groups.parallelStream()
    .<Integer>mapMulti((group, emit) -> {
        for (Integer number : group) {
            emit.accept(number);
        }
    })
    .toList();
```

Với nguồn List có thứ tự, kết quả của `toList()` vẫn theo encounter order: `[1, 2, 3, 4, 5, 6]`. Tuy nhiên, không nên dựa vào thứ tự các mapper bắt đầu hoặc kết thúc để thực hiện tác dụng phụ như ghi log theo trình tự nghiệp vụ. Các mapper của nhiều phần tử nguồn có thể chạy đồng thời.

Nếu terminal operation là `forEach`, hành động có thể được gọi theo thứ tự bất kỳ khi chạy song song. Dùng `forEachOrdered` nếu cần thực hiện hành động cuối theo encounter order:

Tiếp tục dùng danh sách `groups` đã khai báo trong ví dụ parallel Stream ở trên:

```java
groups.parallelStream()
    .<Integer>mapMulti((group, emit) -> {
        group.forEach(emit);
    })
    .forEachOrdered(System.out::println);
```

Trong parallel Stream, không cập nhật collection mutable dùng chung từ mapper. Hãy phát phần tử qua Consumer và để Stream hoặc collector quản lý việc kết hợp kết quả.

## 10. Các thao tác phía sau có thể thay đổi thứ tự

`mapMulti` phát các phần tử theo trình tự của mapper, nhưng các thao tác phía sau có thể thay đổi cách sắp xếp:

- `sorted()` sắp xếp lại phần tử theo thứ tự tự nhiên hoặc comparator.
- `unordered()` bỏ ràng buộc encounter order của pipeline.
- `distinct()` loại bỏ phần tử trùng lặp; với Stream có thứ tự, thao tác này giữ lần xuất hiện đầu tiên theo encounter order.
- `limit()` chỉ giữ một số phần tử đầu theo encounter order nếu pipeline có thứ tự.

Ví dụ, pipeline sau làm phẳng rồi sắp xếp lại kết quả:

```java
import java.util.List;

List<List<Integer>> groups = List.of(
    List.of(3, 1),
    List.of(4, 2, 5)
);

List<Integer> sorted = groups.stream()
    .<Integer>mapMulti((group, emit) -> {
        group.forEach(emit);
    })
    .sorted()
    .toList();
```

Kết quả được sắp xếp theo thứ tự tự nhiên, không còn phản ánh thứ tự ban đầu của các nhóm. Nếu mục tiêu là giữ thứ tự phát, không thêm thao tác làm thay đổi thứ tự sau `mapMulti`.

## 11. Lỗi thường gặp

**Nghĩ rằng mapMulti tự sắp xếp collection.** Phương thức chỉ phát theo thứ tự mapper duyệt và gọi `accept`. Muốn sắp xếp phải dùng collection có thứ tự hoặc thao tác sắp xếp riêng.

**Giả định mọi Collection có thứ tự ổn định.** `List` có thứ tự vị trí, nhưng `HashSet` và `HashMap` không cam kết thứ tự duyệt. Hãy chọn nguồn dữ liệu phù hợp với yêu cầu thứ tự.

**Đảo thứ tự vòng lặp lồng nhau.** Vòng lặp ngoài quyết định nhóm nào được phát trước; vòng lặp trong quyết định thứ tự phần tử trong nhóm. Hãy đặt vòng lặp theo thứ tự nghiệp vụ mong muốn.

**Dùng parallel Stream rồi dựa vào thời điểm mapper chạy.** Các mapper có thể chạy đồng thời. Hãy phân biệt thứ tự kết quả của pipeline có encounter order với thứ tự thực thi tác dụng phụ.

**Thêm unordered() nhưng vẫn mong giữ thứ tự.** Sau khi bỏ ràng buộc encounter order, không dựa vào vị trí đầu ra để biểu diễn thứ tự nghiệp vụ.

**Thêm sorted() rồi mong giữ thứ tự gốc.** `sorted()` thay đổi thứ tự kết quả theo comparator hoặc thứ tự tự nhiên. Chỉ dùng khi thực sự muốn sắp xếp.

**Giữ Consumer để gọi sau mapper.** Hãy gọi `accept` ngay trong lần gọi mapper. Không lưu Consumer để phát kết quả bất đồng bộ sau khi mapper kết thúc.

## 12. Ghi nhớ

- Duyệt collection con và gọi `emit.accept(value)` để làm phẳng dữ liệu.
- Thứ tự gọi `accept` quyết định thứ tự các phần tử được phát trong một mapper.
- Với Stream nguồn có encounter order và collection con có thứ tự duyệt xác định, kết quả làm phẳng giữ thứ tự nguồn và thứ tự bên trong từng collection.
- `List` có thứ tự vị trí; `LinkedHashSet` giữ thứ tự chèn; `TreeSet` theo comparator; `HashSet` không cam kết thứ tự.
- Stream có thứ tự vẫn có thể xử lý song song mà giữ thứ tự kết quả ở các thao tác bảo toàn encounter order như `toList()`.
- Mapper chạy song song có thể thực thi đồng thời; không dựa vào thứ tự tác dụng phụ.
- `sorted()` và `unordered()` có thể làm thay đổi hoặc bỏ ràng buộc thứ tự; hãy dùng khi phù hợp với yêu cầu.
- Chọn `mapMulti` khi vòng lặp phát dữ liệu con rõ ràng; chọn `flatMap` khi Stream con là cách biểu diễn tự nhiên.

Khi hiểu cả thứ tự của Stream nguồn, thứ tự duyệt collection con và thứ tự gọi Consumer, ta có thể làm phẳng collection lồng nhau bằng `mapMulti` mà vẫn giữ đúng trình tự dữ liệu cần thiết cho ứng dụng.

