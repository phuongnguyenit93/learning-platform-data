# Lựa chọn kiểu nguyên thủy hoặc lớp bao theo hợp đồng dữ liệu

## 1. Chọn ý nghĩa dữ liệu trước khi chọn int hay Integer

Câu hỏi quan trọng không chỉ là “hai kiểu này có tự chuyển đổi được không?”, mà là:

> Giá trị này luôn tồn tại, có thể thiếu, chưa biết, hay đang yêu cầu thay đổi một trạng thái khác?

Ví dụ với số lượng hàng:

- `0` có thể nghĩa là đã xác nhận không còn hàng.
- `null` có thể nghĩa là chưa biết số lượng.
- Một trường không được gửi trong yêu cầu cập nhật có thể nghĩa là giữ nguyên dữ liệu cũ.
- Một số âm có thể là dữ liệu không hợp lệ.

Các trạng thái đó không tự đồng nghĩa với nhau.

`int` phù hợp khi hợp đồng yêu cầu luôn có một giá trị số trong miền của nó. `Integer` cần được cân nhắc khi API phải dùng kiểu tham chiếu hoặc cần biểu diễn thêm một trạng thái như `null`.

Tuy nhiên, lớp bao cho phép `null` về mặt kiểu không có nghĩa ứng dụng phải chấp nhận `null` về mặt hợp đồng. Có thể dùng `Integer` trong một collection và vẫn cấm mọi phần tử `null`.

Bài dùng ví dụ chạy trên Java 17 trở lên, tập trung vào lựa chọn kiểu theo dữ liệu và kiểm soát boxing/unboxing tại các ranh giới.

## 2. Primitive và wrapper khác nhau ở điều gì liên quan tới hợp đồng?

| Khía cạnh | Kiểu nguyên thủy, ví dụ int | Lớp bao, ví dụ Integer |
| --- | --- | --- |
| Giá trị số | Có | Có khi tham chiếu khác `null` |
| Trạng thái `null` | Không biểu diễn trực tiếp | Có thể biểu diễn |
| Dùng làm đối số kiểu generic | Không dùng `List<int>` | Dùng được `List<Integer>` |
| Tham gia API nhận Object | Cần boxing | Đã là tham chiếu |
| Dùng trong tính toán | Trực tiếp với giá trị | Thường cần unboxing |
| Tự bảo đảm quy tắc miền như không âm | Không | Không |
| Tự biểu diễn “không gửi” khác “gửi null” | Không | Một tham chiếu nullable thông thường cũng chưa đủ |

Cùng một miền số không có nghĩa cùng một hợp đồng hiện diện dữ liệu. `Integer` chứa `0` và `Integer` có giá trị `null` là hai trạng thái khác nhau.

### Primitive không tự hợp lệ về nghiệp vụ

Một `int quantity` vẫn có thể là `-5`. Nếu số lượng phải không âm, phải kiểm tra.

Một `boolean enabled` luôn là `true` hoặc `false`, nhưng điều đó không chứng minh người dùng đã thực sự cung cấp lựa chọn. Nếu bộ đọc dữ liệu tự đặt giá trị mặc định khi trường bị thiếu, thông tin “đã cung cấp hay chưa” có thể đã mất trước khi logic miền nhận được nó.

Kiểu dữ liệu và xác thực nghiệp vụ cần phối hợp; không bên nào thay thế hoàn toàn bên kia.

## 3. Khi dữ liệu bắt buộc tồn tại, chuẩn hóa về primitive

Giả sử trạng thái tồn kho đã được xác nhận luôn phải có:

- Số lượng không âm.
- Trạng thái bật hoặc tắt rõ ràng.

Một kiểu miền có thể là:

```java
record Inventory(int quantity, boolean enabled) {
    Inventory {
        if (quantity < 0) {
            throw new IllegalArgumentException(
                    "quantity must be non-negative");
        }
    }
}
```

Đây là khai báo kiểu minh họa, có mặt trong chương trình đầy đủ phía sau.

Sau khi một `Inventory` được tạo thành công:

- `quantity` không thể là `null`.
- `enabled` không có trạng thái “chưa biết”.
- Quy tắc không âm được constructor bảo vệ.
- Các phép tính nội bộ không phải kiểm tra nullable wrapper ở mọi bước.

Điều này phù hợp khi sự thiếu dữ liệu là một lỗi cần xử lý **trước khi tạo đối tượng miền**, không phải một trạng thái hợp lệ của chính Inventory.

### Nullable ở đầu vào không bắt buộc nullable ở khắp hệ thống

Một ranh giới có thể nhận `Integer` rồi xác thực và chuyển thành `int`:

```java
static int requireQuantity(Integer value) {
    if (value == null) {
        throw new IllegalArgumentException("quantity is required");
    }
    if (value < 0) {
        throw new IllegalArgumentException(
                "quantity must be non-negative");
    }
    return value;
}
```

Sau kiểm tra `null`, các thao tác unboxing là có chủ đích.

Dòng `return value` cung cấp một `int` cho phần còn lại của chương trình. Thay vì lan truyền `Integer` nullable vào mọi phép tính, ta thiết lập một ranh giới rõ ràng:

```text
Integer dau vao
        |
        v
Xu ly thieu du lieu theo hop dong
        |
        v
Kiem tra mien gia tri
        |
        v
int trong du lieu mien da hop le
```

Không phải mọi hệ thống đều cần cách này, nhưng nó hữu ích khi trạng thái nullable chỉ thuộc đầu vào, không thuộc dữ liệu đã được chấp nhận.

## 4. Khi thiếu giá trị là một trạng thái hợp lệ, phải giữ được nó

Nếu số lượng chưa được kiểm kê là một trạng thái hợp lệ, thay `null` bằng `0` có thể làm sai dữ liệu: “chưa biết” bị biến thành “đã xác nhận bằng không”.

Một trường `Integer quantity` có thể biểu diễn hai trường hợp:

- Có số lượng, kể cả `0`.
- Không có giá trị số tại thời điểm này.

Hợp đồng cần nói rõ `null` nghĩa là gì. Những nghĩa như “chưa biết”, “không áp dụng”, “chưa tải” và “không được gửi” có thể đòi cách xử lý khác nhau. Không dùng một `null` duy nhất nếu các nghĩa đó cần được phân biệt trong cùng API.

### Khi ba trạng thái có tên riêng, có thể dùng enum

Nếu một cấu hình bật/tắt còn có trạng thái kế thừa, một enum có thể rõ hơn `Boolean` nullable:

```java
enum SwitchSetting {
    ON,
    OFF,
    INHERIT
}
```

`INHERIT` nói rõ ý nghĩa hơn một giá trị `null` không được giải thích.

Một mô hình cần phân biệt “đang tải”, “lỗi tải” và “đã có giá trị” cũng thường cần cấu trúc trạng thái rõ ràng hơn việc để một wrapper nullable gánh mọi trường hợp.

Chọn wrapper là một lựa chọn biểu diễn, không phải lời giải mặc định cho mọi loại thiếu dữ liệu.

## 5. Cập nhật một phần: null, 0 và false cần được phân biệt

Trong một lệnh cập nhật một phần, có thể quy định:

- `quantity == null`: không thay đổi số lượng hiện tại.
- `quantity == 0`: chủ động đặt số lượng thành `0`.
- `enabled == null`: không thay đổi trạng thái hiện tại.
- `enabled == false`: chủ động tắt.

Vì vậy, một kiểu lệnh có thể dùng wrapper:

```java
record InventoryPatch(Integer quantity, Boolean enabled)
```

Đây là hình dạng khai báo; bản có kiểm tra dữ liệu nằm trong chương trình đầy đủ.

Nếu dùng ngay `int` và `boolean` mà không có thông tin hiện diện bổ sung, các giá trị `0` và `false` không đủ nói lên trường nào được yêu cầu cập nhật.

Không được viết logic “chỉ cập nhật nếu số lớn hơn `0`” khi `0` là một giá trị cập nhật hợp lệ. Tương tự, chỉ kiểm tra `Boolean.TRUE` sẽ bỏ qua yêu cầu tắt nếu hợp đồng cần xử lý cả hai giá trị rõ ràng.

### Khi cần “không gửi”, “xóa” và “đặt giá trị”, hai trạng thái chưa đủ

Ví dụ Patch trong bài gộp `null` vào nghĩa “không thay đổi” và không hỗ trợ lệnh xóa giá trị.

Nếu một API phải phân biệt:

1. Không gửi trường.
2. Gửi yêu cầu xóa giá trị.
3. Gửi một giá trị mới.

thì một thuộc tính `Integer` nullable đơn thuần không đủ chứa cả ba thông tin. Cần metadata hiện diện hoặc một kiểu lệnh có các trạng thái tường minh.

Điều này đặc biệt cần kiểm tra ở ranh giới đọc JSON, biểu mẫu, cấu hình hoặc dữ liệu từ thư viện. Cách phân biệt trường vắng mặt với trường có `null` phụ thuộc hợp đồng của bộ đọc; đừng giả định chỉ thay primitive bằng wrapper là toàn bộ thông tin hiện diện đã được giữ.

## 6. Chương trình đầy đủ: nullable ở lệnh, primitive ở trạng thái đã hợp lệ

Lưu thành `PrimitiveWrapperContractDemo.java`:

```java
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.OptionalInt;

public class PrimitiveWrapperContractDemo {
    record Inventory(int quantity, boolean enabled) {
        Inventory {
            if (quantity < 0) {
                throw new IllegalArgumentException(
                        "quantity must be non-negative");
            }
        }
    }

    record InventoryPatch(Integer quantity, Boolean enabled) {
        InventoryPatch {
            if (quantity != null && quantity < 0) {
                throw new IllegalArgumentException(
                        "patch quantity must be non-negative");
            }
        }
    }

    static Inventory applyPatch(
            Inventory current, InventoryPatch patch) {
        Objects.requireNonNull(current, "current");
        Objects.requireNonNull(patch, "patch");

        int quantity = patch.quantity() == null
                ? current.quantity()
                : patch.quantity();
        boolean enabled = patch.enabled() == null
                ? current.enabled()
                : patch.enabled();
        return new Inventory(quantity, enabled);
    }

    static int requireQuantity(Integer value) {
        if (value == null) {
            throw new IllegalArgumentException("quantity is required");
        }
        if (value < 0) {
            throw new IllegalArgumentException(
                    "quantity must be non-negative");
        }
        return value;
    }

    static OptionalInt findIndex(List<String> values, String target) {
        Objects.requireNonNull(values, "values");
        Objects.requireNonNull(target, "target");
        for (int index = 0; index < values.size(); index++) {
            if (target.equals(values.get(index))) {
                return OptionalInt.of(index);
            }
        }
        return OptionalInt.empty();
    }

    public static void main(String[] args) {
        Inventory current = new Inventory(12, true);
        System.out.println("unchanged = "
                + applyPatch(current, new InventoryPatch(null, null)));
        System.out.println("explicit zero and false = "
                + applyPatch(current, new InventoryPatch(0, false)));
        System.out.println("quantity only = "
                + applyPatch(current, new InventoryPatch(5, null)));

        System.out.println("validated zero = " + requireQuantity(0));
        try {
            requireQuantity(null);
        } catch (IllegalArgumentException exception) {
            System.out.println(exception.getMessage());
        }

        Boolean unknown = null;
        try {
            if (unknown) {
                System.out.println("enabled");
            }
        } catch (NullPointerException exception) {
            System.out.println("nullable Boolean requires a policy");
        }
        System.out.println("only explicit true enables = "
                + Boolean.TRUE.equals(unknown));

        List<String> names = List.of("An", "Binh");
        OptionalInt first = findIndex(names, "An");
        OptionalInt absent = findIndex(names, "Chi");
        System.out.println("first index present = " + first.isPresent());
        System.out.println("first index value = " + first.orElseThrow());
        System.out.println("missing index present = " + absent.isPresent());

        Map<String, Integer> observed = new HashMap<>();
        observed.put("zero", 0);
        observed.put("unknown", null);
        System.out.println("zero value = " + observed.get("zero"));
        System.out.println("unknown value = " + observed.get("unknown"));
        System.out.println("unknown key present = "
                + observed.containsKey("unknown"));
        System.out.println("missing key present = "
                + observed.containsKey("missing"));

        System.out.println("new int array = "
                + Arrays.toString(new int[2]));
        System.out.println("new Integer array = "
                + Arrays.toString(new Integer[2]));

        List<Integer> counts = List.of(1, 2, 3);
        int total = 0;
        for (int count : counts) {
            total += count;
        }
        System.out.println("generic counts sum = " + total);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror PrimitiveWrapperContractDemo.java
java PrimitiveWrapperContractDemo
```

Stdout:

```text
unchanged = Inventory[quantity=12, enabled=true]
explicit zero and false = Inventory[quantity=0, enabled=false]
quantity only = Inventory[quantity=5, enabled=true]
validated zero = 0
quantity is required
nullable Boolean requires a policy
only explicit true enables = false
first index present = true
first index value = 0
missing index present = false
zero value = 0
unknown value = null
unknown key present = true
missing key present = false
new int array = [0, 0]
new Integer array = [null, null]
generic counts sum = 6
```

### 6.1. Giá trị 0 và false được giữ đúng ý nghĩa

`new InventoryPatch(0, false)` tạo một yêu cầu cập nhật rõ ràng. Kết quả là `quantity=0` và `enabled=false`.

Hai giá trị đó không bị coi là “thiếu”. Đây là điểm phân biệt quan trọng nhất giữa kiểm tra hiện diện và kiểm tra giá trị.

### 6.2. null được giải quyết trước khi unbox

Trong `applyPatch`:

```java
int quantity = patch.quantity() == null
        ? current.quantity()
        : patch.quantity();
```

Nhánh lấy giá trị wrapper chỉ được dùng khi đã biết nó khác `null`. Nếu thiếu, chọn giá trị primitive hiện tại.

Cùng một chính sách được dùng cho `Boolean enabled`. Không có một bước unboxing nullable không được giải thích.

Constructor của Patch từ chối số lượng âm nếu có giá trị. Constructor Inventory tiếp tục giữ quy tắc của trạng thái miền.

### 6.3. Một đối tượng mới biểu diễn trạng thái sau cập nhật

`applyPatch` trả một Inventory mới. Nó không đặt `null` vào trạng thái hiện tại hoặc để việc cập nhật một trường làm trường khác trở nên chưa xác định.

Đó là quyết định của ví dụ để hợp đồng dễ kiểm tra, không phải yêu cầu rằng mọi ứng dụng phải dùng record hoặc cập nhật bất biến.

## 7. Boolean nullable cần chính sách, không chỉ một phép if

Với:

```java
Boolean enabled = null;
// if (enabled) { } // Neu thuc hien: NullPointerException
```

điều kiện `if` cần `boolean`, nên Java phải unbox `Boolean`. `null` không có giá trị primitive để lấy ra.

Quy tắc unboxing `null` gây `NullPointerException` nằm ở [JLS: Unboxing Conversion](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.8).

Có thể dùng:

```java
boolean shouldEnable = Boolean.TRUE.equals(enabled);
```

Câu lệnh này an toàn với `null`, nhưng nó áp dụng một chính sách cụ thể: **chỉ giá trị true tường minh mới bật**. Cả `false` và `null` cho kết quả `false`.

Nếu `null` nghĩa là dữ liệu bắt buộc đang thiếu, cách đó che mất lỗi. Nếu `null` nghĩa là kế thừa cấu hình khác, cách đó cũng chưa thực hiện chính sách kế thừa.

Những lựa chọn hợp lệ tùy hợp đồng:

- Từ chối `null` vì giá trị bắt buộc.
- Giữ nguyên giá trị cũ trong cập nhật một phần.
- Lấy từ cấu hình cha.
- Dùng một giá trị mặc định được công bố.
- Biểu diễn trạng thái thiếu bằng một kiểu miền riêng.

Một câu lệnh không ném ngoại lệ chưa chắc là câu lệnh giữ đúng ý nghĩa dữ liệu.

## 8. Kết quả có thể không tồn tại: OptionalInt giữ được cả giá trị 0

Khi một phương thức có thể tìm thấy chỉ số hoặc không tìm thấy, `0` không thích hợp làm giá trị đánh dấu “không có” vì nó là chỉ số hợp lệ.

Ví dụ dùng:

```java
static OptionalInt findIndex(List<String> values, String target)
```

Đây là chữ ký của phương thức trong chương trình.

Kết quả:

- Tìm `"An"` ở vị trí đầu: `OptionalInt` có giá trị `0`.
- Không tìm thấy `"Chi"`: `OptionalInt.empty()`.

`OptionalInt` biểu diễn “có một giá trị int” hoặc “không có kết quả int” mà không mượn một số trong miền làm dấu hiệu ngầm. Chính biến `OptionalInt` không nên là `null`.

API này chủ yếu được thiết kế cho kết quả phương thức có thể vắng mặt; xem [OptionalInt](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/OptionalInt.html).

Không cần thay mọi tham số hoặc trường wrapper bằng OptionalInt theo máy móc. Hãy chọn theo vai trò: một kết quả tìm kiếm có thể vắng mặt khác một trường bắt buộc trong trạng thái miền hoặc một trường tùy chọn ở lệnh cập nhật.

### Giá trị mặc định vẫn là một quyết định nghiệp vụ

Gọi `orElse(0)` sẽ biến “không có kết quả” thành `0`. Điều đó chỉ đúng nếu hợp đồng cho phép việc gộp hai trạng thái.

Trong bài, ta đọc `isPresent()` và chỉ lấy giá trị của kết quả đã có để chứng minh rằng chỉ số `0` vẫn được phân biệt với không tìm thấy.

Một giá trị đánh dấu như `-1` cũng có thể là hợp đồng hợp lệ của một API chỉ số đã được công bố. Điểm cần tránh là tự chọn một giá trị đánh dấu mơ hồ hoặc làm mất nghĩa khi đổi sang wrapper hoặc primitive.

## 9. Generic cần wrapper nhưng không tự quyết định nullability

Java không cho dùng kiểu nguyên thủy làm đối số kiểu:

```java
// List<int> counts; // Khong bien dich
List<Integer> counts = List.of(1, 2, 3);
```

Trong ví dụ này, wrapper là lựa chọn bắt buộc để đi qua API generic. Nó không có nghĩa “mỗi phần tử có thể thiếu”.

`List.of` không chấp nhận phần tử `null`. Vì vậy, vòng lặp lấy `int` để cộng tổng trong chương trình phù hợp với dữ liệu đã tạo.

Ngược lại, một `ArrayList<Integer>` có thể chứa `null` nếu ứng dụng thêm vào. Vòng lặp unbox các phần tử đó cần một chính sách dữ liệu rõ ràng.

Các câu hỏi cần tách biệt:

1. API kỹ thuật có đòi kiểu tham chiếu không?
2. Hợp đồng phần tử có cho phép `null` không?
3. Khi đi vào tính toán primitive, thiếu dữ liệu được giải quyết ở đâu?

Chỉ nhìn thấy `Integer` không trả lời được cả ba câu hỏi.

### Mảng primitive và mảng wrapper cũng khác hợp đồng

`int[]` mới chứa các giá trị khởi tạo `0`. `Integer[]` mới chứa các tham chiếu `null`.

Do đó, chọn `Integer[]` cho một nhóm dữ liệu có thể thêm các trạng thái thiếu vào mỗi ô. Chọn `int[]` làm mất khả năng dùng `null` ở từng ô nhưng không tự nói rằng các giá trị `0` đã được nhập hoặc đã được xác nhận.

Nếu cần theo dõi “ô đã được cung cấp hay chưa” và vẫn dùng mảng primitive, phải lưu thông tin hiện diện bằng một cơ chế riêng.

## 10. Map.get có thể cần phân biệt không có khóa với có giá trị null

Chương trình dùng một `HashMap<String, Integer>`:

- Khóa `"zero"` ánh xạ tới `0`.
- Khóa `"unknown"` tồn tại nhưng có giá trị `null`.
- Khóa `"missing"` không tồn tại.

`get("unknown")` và `get("missing")` đều có thể trả `null` trong loại Map này. Khi ý nghĩa khác nhau, `containsKey` giúp phân biệt.

Điều này nằm trong hợp đồng của [Map.get](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html#get(java.lang.Object)).

Không unbox kết quả `Map.get` ngay chỉ vì kiểu khai báo là `Integer`:

```java
// int count = observed.get("missing"); // Unboxing null se gay loi
```

Phải xác định “không có khóa” là lỗi, giá trị mặc định hay một kết quả vắng mặt hợp lệ.

Cũng không mặc định mọi Map cho phép giá trị `null`. Chính sách phụ thuộc cách cài đặt và API tạo Map; lựa chọn kiểu generic không tự công bố toàn bộ hành vi đó.

## 11. Giá trị khởi tạo mặc định không chứng minh dữ liệu đã được cung cấp

Đối với trường đối tượng và phần tử mảng, Java cung cấp giá trị khởi tạo mặc định:

- `int`: `0`.
- `boolean`: `false`.
- Tham chiếu như `Integer` hoặc `Boolean`: `null`.

Quy tắc này khác với biến cục bộ chưa được gán trong phương thức; biến cục bộ cần được gán chắc chắn trước khi đọc.

Các quy tắc nằm ở [JLS: Initial Values of Variables](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.12.5).

Từ đó cần tránh suy luận:

- “Có `quantity=0` nên người dùng đã nhập số lượng bằng không.”
- “Có `enabled=false` nên người dùng đã chủ động tắt.”
- “Đổi trường sang Integer là bộ đọc tự phân biệt mọi dạng thiếu dữ liệu.”

Khi đi qua bộ ánh xạ dữ liệu, cần kiểm tra hợp đồng thực tế của nó: thiếu trường, `null` tường minh, giá trị không đúng kiểu và mặc định được xử lý thế nào. Không tự suy ra quy tắc của một framework chỉ từ kiểu Java.

## 12. Cân nhắc hiệu năng sau khi giữ đúng ý nghĩa dữ liệu

Trong tính toán thường xuyên hoặc một nhóm số lớn, primitive có thể tránh các đường boxing/unboxing không cần thiết. Một bộ đếm nội bộ luôn có giá trị thường nên được mô tả trực tiếp bằng primitive.

Tuy nhiên:

- Không tuyên bố mỗi lần boxing chắc chắn tạo một đối tượng mới trong mọi cách chạy.
- Không đổi `null` thành `0` chỉ để loại wrapper nếu việc đó làm sai ý nghĩa.
- Không kết luận một biến đổi nhanh hơn chỉ từ cú pháp; khi hiệu năng là yêu cầu thực sự, cần đo trên tác vụ và JVM phù hợp.
- Không chọn wrapper chỉ vì muốn dùng một cú pháp API nếu có lựa chọn primitive phù hợp với cùng hợp đồng.

Giữ ranh giới rõ ràng thường giúp cả hai phía: wrapper hoặc kiểu trạng thái ở nơi cần mô tả hiện diện dữ liệu, primitive trong phần tính toán đã được xác thực.

## 13. Bảng quyết định theo tình huống

| Tình huống | Hướng chọn kiểu |
| --- | --- |
| Bộ đếm nội bộ luôn có giá trị | Primitive, ví dụ `int` hoặc `long` theo miền |
| Trạng thái miền bắt buộc có số lượng | Primitive cùng kiểm tra quy tắc miền |
| Đầu vào có thể thiếu và thiếu là lỗi | Có thể nhận wrapper ở biên, từ chối thiếu rồi chuẩn hóa |
| Số đo chưa biết là trạng thái hợp lệ | Wrapper nullable có tài liệu hoặc kiểu trạng thái riêng |
| Cập nhật một phần cần phân biệt giữ nguyên với đặt 0/false | Wrapper hoặc biểu diễn hiện diện tường minh |
| Cần phân biệt không gửi, xóa và đặt giá trị | Kiểu lệnh hoặc metadata hiện diện, không chỉ một wrapper |
| Kết quả phương thức có thể không có một số int | Cân nhắc `OptionalInt` |
| `List`, `Map` generic cần giữ số nguyên | Wrapper; quyết định thêm chính sách `null` |
| Ba trạng thái cấu hình có nghĩa miền riêng | Cân nhắc enum có tên rõ ràng |

Không có một quy tắc “luôn primitive” hoặc “luôn wrapper” đáp ứng mọi hàng trong bảng. Quyết định phụ thuộc vào các trạng thái mà dữ liệu phải giữ được qua API.

## 14. Những lỗi thiết kế thường gặp

### Thay null bằng 0 ở mọi nơi

Làm mất phân biệt giữa “không có dữ liệu” và “giá trị đã biết bằng không”. Chỉ áp dụng nếu hợp đồng thật sự công bố một giá trị mặc định như vậy.

### Dùng wrapper cho mọi trường để linh hoạt

Làm lan truyền trạng thái `null` vào những nơi không có ý nghĩa nghiệp vụ cho nó. Mã tính toán phải kiểm tra thiếu dữ liệu lặp lại và dễ gặp unboxing ngoài ý muốn.

### Coi primitive là xác thực bắt buộc

Một giá trị primitive có thể đến từ mặc định của bộ đọc. Nếu bắt buộc người gọi phải cung cấp, xác thực hiện diện trước khi thông tin bị gộp vào một giá trị mặc định.

### Dùng Boolean.TRUE.equals để che mọi dữ liệu thiếu

An toàn với `null` về mặt thực thi không đồng nghĩa đúng về hợp đồng. Câu lệnh áp dụng chính sách “không true thì không bật”; chưa chắc đó là nghĩa mong muốn.

### Chỉ kiểm tra quantity > 0 khi cập nhật

Bỏ qua yêu cầu đặt số lượng thành `0` nếu `0` là dữ liệu hợp lệ. Phải kiểm tra hiện diện riêng với kiểm tra miền giá trị.

### Để unboxing ở xa ranh giới

Một `Integer` nullable có thể đi qua nhiều lớp rồi mới gây lỗi trong phép cộng. Xử lý thiếu dữ liệu tại nơi biết rõ ý nghĩa của nó giúp lỗi và chính sách dễ hiểu hơn.

## 15. Thực hành tự kiểm tra

### Bài 1: Số lượng bằng 0

Nếu `0` nghĩa là xác nhận hết hàng, có nên dùng `0` cho cả “chưa kiểm kê” không?

**Đáp án:** không nếu hai trạng thái cần được phân biệt. Dùng biểu diễn thiếu hoặc một trạng thái có tên rõ ràng.

### Bài 2: Lệnh cập nhật tắt trạng thái

Trong hợp đồng Patch của bài, `enabled=false` có giống `enabled=null` không?

**Đáp án:** không. `false` là yêu cầu tắt; `null` là giữ nguyên trạng thái hiện tại.

### Bài 3: Generic và null

`List<Integer>` có tự nói mọi phần tử đều được phép `null` không?

**Đáp án:** không. Wrapper cần cho generic, còn quyền có `null` phụ thuộc hợp đồng dữ liệu và collection.

### Bài 4: Tìm chỉ số đầu tiên

`OptionalInt.of(0)` và `OptionalInt.empty()` có cùng ý nghĩa không?

**Đáp án:** không. Một bên có kết quả là chỉ số `0`; một bên không có kết quả.

### Bài 5: Primitive bắt buộc

Một trường `int age` tự có giá trị mặc định `0`. Điều đó chứng minh người dùng đã cung cấp tuổi chưa?

**Đáp án:** chưa. Cần xác thực hiện diện ở ranh giới đọc dữ liệu theo hợp đồng của ứng dụng.

### Bài 6: Chuẩn hóa

Nếu số lượng bắt buộc tồn tại và không âm, vì sao nhận `Integer` rồi trả `int` sau xác thực có thể hợp lý?

**Đáp án:** wrapper giữ được trạng thái thiếu ở đầu vào; kiểm tra giải quyết trạng thái đó; primitive trong phần miền sau đó biểu diễn rõ rằng giá trị đã tồn tại và không cần nullable.

Hãy chọn kiểu theo các trạng thái cần giữ, xác định chính sách thiếu dữ liệu tại ranh giới và chỉ chuyển sang primitive khi hợp đồng đã bảo đảm có giá trị. Boxing/unboxing nên phục vụ hợp đồng đó thay vì vô tình quyết định ý nghĩa của dữ liệu.
