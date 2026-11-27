# Duyệt ApplicationModule bằng stream

Khi cần quan sát cấu trúc của một modular monolith, ta thường muốn liệt kê các mô-đun, tìm mô-đun theo tên, lọc một nhóm mô-đun hoặc tạo báo cáo về mô hình kiến trúc. Spring Modulith biểu diễn cấu trúc đó bằng `ApplicationModules` và từng phần tử `ApplicationModule`. Có thể duyệt tập mô-đun bằng Java Stream API để thực hiện các thao tác này theo một pipeline rõ ràng.

Trong phạm vi **SPRING_MODULITH_MODULE_MODEL**, `ApplicationModules` giúp xác định ranh giới nghiệp vụ, API công khai và phụ thuộc giữa các package trong ứng dụng Spring Boot. Việc duyệt `ApplicationModule` bằng stream là cách khai thác mô hình đã được khám phá: ta có thể chọn đúng những mô-đun cần quan sát, chuyển chúng thành dữ liệu phục vụ báo cáo hoặc tìm một mô-đun đáp ứng điều kiện. Stream không tự kiểm chứng kiến trúc; khi cần xác nhận các quy tắc phụ thuộc, vẫn phải gọi `verify()` riêng.

## 1. Phân biệt ApplicationModules và ApplicationModule

Hai kiểu dữ liệu có vai trò khác nhau:

- `ApplicationModules` đại diện cho mô hình gồm các application module được Spring Modulith khám phá trong ứng dụng.
- `ApplicationModule` đại diện cho một mô-đun cụ thể, chẳng hạn `orders`, `inventory` hoặc `customers`.

Ta tạo mô hình từ lớp ứng dụng Spring Boot:

```java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
```

`ShopApplication` là lớp ứng dụng gốc trong ví dụ. Spring Modulith dùng cấu trúc package của ứng dụng để khám phá các mô-đun theo quy ước và metadata đã khai báo. Sau khi có `ApplicationModules`, ta có thể duyệt các phần tử bằng `stream()`:

```java
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

modules.stream()
    .forEach(module -> System.out.println(module.getName()));
```

Mỗi phần tử trong stream là một `ApplicationModule`. `getName()` trả về tên mô-đun, thuận tiện để hiển thị, lọc hoặc chuyển thành dữ liệu đơn giản. Ví dụ, nếu ứng dụng có các mô-đun `orders`, `inventory` và `customers`, pipeline trên sẽ in tên từng mô-đun.

## 2. Hiểu pipeline của Stream API

Một pipeline stream thường có ba phần:

1. **Nguồn dữ liệu:** `modules.stream()` tạo stream từ các mô-đun đã được khám phá.
2. **Các thao tác trung gian:** `filter`, `map`, `sorted`, `distinct` biến đổi hoặc chọn phần tử. Chúng trả về một stream mới và thường được thực thi lười.
3. **Thao tác kết thúc:** `forEach`, `collect`, `count`, `findFirst`, `anyMatch` tiêu thụ stream và tạo kết quả hoặc thực hiện hành động cuối cùng.

Ví dụ, chỉ lấy tên mô-đun rồi sắp xếp trước khi in:

```java
modules.stream()
    .map(ApplicationModule::getName)
    .sorted()
    .forEach(System.out::println);
```

`map` chuyển mỗi `ApplicationModule` thành một chuỗi tên. `sorted` sắp xếp các chuỗi đó. `forEach` là thao tác kết thúc khiến pipeline được thực thi.

Các thao tác trung gian không tự duyệt toàn bộ dữ liệu ngay khi được gọi. Vì vậy, đoạn sau chưa in gì cho đến khi có thao tác kết thúc:

```java
var names = modules.stream()
    .map(ApplicationModule::getName)
    .sorted();

// Pipeline chưa được tiêu thụ tại đây.
names.forEach(System.out::println);
```

Một stream chỉ được tiêu thụ một lần. Sau khi gọi `forEach`, `collect` hoặc một thao tác kết thúc khác, không thể dùng lại chính stream đó. Nếu cần chạy một phép xử lý khác, hãy gọi `modules.stream()` để tạo stream mới.

## 3. Lọc mô-đun bằng filter

`filter` giữ lại các phần tử thỏa mãn một điều kiện. Ví dụ, tìm những mô-đun có tên bắt đầu bằng `order`:

```java
modules.stream()
    .filter(module -> module.getName().startsWith("order"))
    .forEach(module -> System.out.println(module.getName()));
```

Điều kiện trong `filter` nhận một `ApplicationModule` và trả về `boolean`. Có thể kết hợp nhiều điều kiện:

```java
modules.stream()
    .filter(module -> module.getName().startsWith("order"))
    .filter(module -> !module.getName().endsWith("archive"))
    .map(ApplicationModule::getName)
    .forEach(System.out::println);
```

Hai thao tác `filter` được áp dụng nối tiếp. Cách viết này giúp mỗi điều kiện có một mục đích rõ ràng. Nếu điều kiện ngắn và liên quan chặt chẽ, cũng có thể kết hợp chúng trong một predicate.

Lọc theo tên phù hợp khi cần tạo danh sách theo quy ước đặt tên hoặc chọn một nhóm đã biết. Nếu logic chọn mô-đun dựa trên trách nhiệm nghiệp vụ, hãy cân nhắc biểu diễn trách nhiệm đó bằng metadata hoặc cấu trúc mô-đun phù hợp; tránh phụ thuộc lâu dài vào quy tắc đặt tên mong manh.

## 4. Chuyển mô-đun thành dữ liệu bằng map

Không phải lúc nào phần còn lại của chương trình cũng cần giữ toàn bộ đối tượng `ApplicationModule`. Khi tạo báo cáo, log hoặc danh sách hiển thị, thường chỉ cần một vài giá trị như tên mô-đun.

```java
import java.util.List;
import java.util.stream.Collectors;

List<String> moduleNames = modules.stream()
    .map(ApplicationModule::getName)
    .sorted()
    .collect(Collectors.toList());
```

Sau thao tác `collect`, `moduleNames` là một danh sách tên độc lập để truyền cho lớp báo cáo hoặc dùng trong kiểm thử. `map` thay đổi kiểu phần tử của stream từ `ApplicationModule` sang `String`.

Có thể ánh xạ thành một dòng báo cáo có định dạng riêng:

```java
List<String> reportLines = modules.stream()
    .sorted((left, right) -> left.getName().compareTo(right.getName()))
    .map(module -> "Module: " + module.getName())
    .collect(Collectors.toList());
```

Trong ví dụ này, sắp xếp diễn ra khi phần tử vẫn là `ApplicationModule`, sau đó `map` chuyển mỗi mô-đun thành một dòng văn bản. Việc sắp xếp giúp kết quả ổn định, dễ đọc và dễ so sánh giữa các lần chạy.

## 5. Tìm kiếm và kiểm tra điều kiện

Khi cần lấy một mô-đun thỏa mãn điều kiện, dùng `findFirst()`:

```java
import java.util.Optional;

Optional<ApplicationModule> orders = modules.stream()
    .filter(module -> module.getName().equals("orders"))
    .findFirst();

orders.ifPresent(module ->
    System.out.println("Found module: " + module.getName())
);
```

`findFirst()` trả về `Optional<ApplicationModule>` vì có thể không có phần tử nào phù hợp. Dùng `ifPresent`, `orElse` hoặc `orElseThrow` để xử lý trường hợp có và không có kết quả. Không nên gọi `get()` trực tiếp nếu chưa kiểm tra `Optional`.

Nếu chỉ cần biết có tồn tại mô-đun thỏa mãn điều kiện hay không, dùng `anyMatch`:

```java
boolean hasOrdersModule = modules.stream()
    .anyMatch(module -> module.getName().equals("orders"));
```

Các thao tác kiểm tra khác có thể dùng trong tình huống tương ứng:

| Thao tác | Ý nghĩa | Kết quả |
|---|---|---|
| `anyMatch(predicate)` | Có ít nhất một mô-đun thỏa điều kiện? | `boolean` |
| `allMatch(predicate)` | Tất cả mô-đun có thỏa điều kiện? | `boolean` |
| `noneMatch(predicate)` | Không có mô-đun nào thỏa điều kiện? | `boolean` |
| `findFirst()` | Lấy phần tử đầu tiên theo thứ tự duyệt | `Optional<ApplicationModule>` |
| `count()` | Đếm số mô-đun | `long` |

Các thao tác như `anyMatch` và `findFirst` có thể dừng sớm khi đã có kết quả. Điều này hữu ích khi chỉ cần trả lời một câu hỏi thay vì tạo toàn bộ danh sách.

## 6. Tổng hợp thông tin và tạo báo cáo

Stream cũng hữu ích khi cần tổng hợp thông tin từ mô hình mô-đun. Ví dụ, đếm số mô-đun được khám phá:

```java
long moduleCount = modules.stream().count();
System.out.println("Application modules: " + moduleCount);
```

Hoặc tạo danh sách tên đã sắp xếp để hiển thị trong báo cáo kiến trúc:

```java
List<String> moduleNames = modules.stream()
    .map(ApplicationModule::getName)
    .distinct()
    .sorted()
    .collect(Collectors.toList());

System.out.println("Discovered modules:");
moduleNames.forEach(name -> System.out.println("- " + name));
```

`distinct()` loại bỏ giá trị trùng theo quy tắc `equals` và `hashCode` của phần tử trong stream. Với ví dụ tên mô-đun, thao tác này không phải lúc nào cũng cần thiết vì tên mô-đun vốn được định danh trong mô hình; nó minh họa cách khử trùng lặp khi pipeline có thể tạo ra dữ liệu lặp.

Nếu cần nhiều chỉ số từ cùng một mô hình, hãy cân nhắc tạo một đối tượng kết quả báo cáo sau khi thực hiện các phép tổng hợp cần thiết. Không nên thu thập toàn bộ đối tượng vào nhiều danh sách chỉ để tính một giá trị đơn giản.

## 7. Ví dụ hoàn chỉnh trong một bài kiểm thử

Một bài kiểm thử có thể dùng stream để xác nhận ứng dụng đã khám phá được những mô-đun mong đợi và tạo danh sách tên ổn định:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

class ApplicationModuleStreamTests {

    @Test
    void listsDiscoveredModules() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        List<String> names = modules.stream()
            .map(ApplicationModule::getName)
            .sorted()
            .collect(Collectors.toList());

        assertThat(names).contains("orders", "inventory");
    }
}
```

Ví dụ giả định ứng dụng có các mô-đun `orders` và `inventory`. Trong dự án thực tế, thay `ShopApplication.class` bằng lớp ứng dụng gốc và thay các tên trong assertion bằng tên mô-đun đã khai báo. Bài kiểm thử này kiểm tra kết quả khám phá và cách chuyển dữ liệu bằng stream; nó chưa kiểm tra các quy tắc phụ thuộc giữa mô-đun.

Nếu muốn xác minh cả cấu trúc kiến trúc, hãy thực hiện kiểm tra riêng:

```java
ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
modules.verify();
```

`verify()` kiểm tra mô hình theo các quy tắc kiến trúc Spring Modulith áp dụng. Việc duyệt stream và việc xác minh kiến trúc giải quyết hai nhu cầu khác nhau: một bên giúp truy vấn hoặc trình bày mô hình, bên kia kiểm tra tính hợp lệ của cấu trúc.

## 8. Lưu ý khi sử dụng stream

- **Tạo stream mới cho mỗi lần duyệt.** Không lưu một stream đã tiêu thụ để tái sử dụng. Hãy giữ `ApplicationModules` làm mô hình nguồn và gọi `stream()` cho từng pipeline.
- **Ưu tiên pipeline không có side effect.** Dùng `map` để chuyển đổi và `filter` để chọn phần tử. Hạn chế cập nhật trạng thái bên ngoài trong các thao tác trung gian.
- **Không dùng `peek` cho logic nghiệp vụ.** `peek` có thể hữu ích khi gỡ lỗi pipeline, nhưng hành vi của nó phụ thuộc vào việc pipeline có được tiêu thụ và phần tử có đi qua vị trí đó hay không.
- **Sắp xếp khi cần kết quả ổn định.** Nếu xuất báo cáo, sinh snapshot hoặc so sánh kết quả kiểm thử, hãy dùng `sorted()` thay vì dựa vào thứ tự duyệt mặc định.
- **Chọn thao tác phù hợp với kết quả cần có.** Dùng `anyMatch` nếu chỉ cần câu trả lời đúng/sai; dùng `findFirst` nếu cần một phần tử; dùng `collect` nếu thực sự cần danh sách.
- **Tránh parallel stream cho mô hình nhỏ.** Duyệt metadata mô-đun thường không phải tác vụ tính toán nặng. Parallel stream có thể làm luồng xử lý khó hiểu hơn mà không mang lại lợi ích đáng kể.
- **Không nhầm truy vấn mô hình với kiểm chứng mô hình.** Lọc được một mô-đun hoặc in ra toàn bộ tên không chứng minh rằng các phụ thuộc đều hợp lệ. Hãy gọi `verify()` khi mục tiêu là kiểm tra quy tắc kiến trúc.

## Kết luận

`ApplicationModules.stream()` cung cấp cách tự nhiên để duyệt các `ApplicationModule` đã được Spring Modulith khám phá. Kết hợp `filter`, `map`, `sorted`, `findFirst`, `anyMatch` và `collect`, ta có thể tìm mô-đun, tạo danh sách, kiểm tra điều kiện và xây dựng báo cáo kiến trúc bằng những pipeline ngắn, dễ đọc. Hãy xem `ApplicationModules` là nguồn của mô hình, tạo stream mới cho mỗi phép xử lý và dùng `verify()` riêng khi cần bảo vệ các quy tắc phụ thuộc của modular monolith.
