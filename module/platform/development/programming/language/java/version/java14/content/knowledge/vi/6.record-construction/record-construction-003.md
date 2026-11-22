# Kiểm tra điều kiện hợp lệ của dữ liệu đầu vào khi khởi tạo record

## Mục tiêu

Một `record` mô tả dữ liệu thông qua các **record components**; các trường tương ứng là `private final`, nhưng **Java không tự kiểm tra dữ liệu nghiệp vụ** chỉ vì bạn khai báo `record`. Ví dụ, `record Quantity(int value) {}` vẫn cho phép `new Quantity(-3)` trừ khi có quy tắc kiểm tra do bạn viết.

Sau bài này, bạn sẽ:

- Xác định **bất biến (invariant)** mà mọi thể hiện `record` hợp lệ phải duy trì.
- Thực hiện kiểm tra `null`, chuỗi rỗng, giới hạn số, quan hệ giữa các components và phần tử trong tập hợp **ngay trong canonical constructor**.
- Dùng **compact canonical constructor** để kiểm tra và chuẩn hóa tham số mà không tự gán các component fields.
- Biết khi nào dùng **normal canonical constructor**, cách để các constructor bổ sung không bỏ qua validation và cách xử lý lỗi có ý nghĩa.
- Phòng trường hợp dữ liệu hợp lệ lúc khởi tạo nhưng sau đó bị thay đổi qua một tham chiếu mutable, nhờ **defensive copy**.
- Biên dịch và chạy chương trình Java 17+ có kiểm tra cả đầu vào hợp lệ lẫn đầu vào sai.

**Phạm vi phiên bản:** Records được giới thiệu dạng **preview ở Java 14**, nhưng đã trở thành **tính năng chuẩn từ Java 16** ([JEP 395](https://openjdk.org/jeps/395)). Nội dung dưới đây sử dụng cú pháp và hành vi **đang được hỗ trợ trong Java hiện đại**, với ví dụ biên dịch bằng `--release 17`. Không dùng cú pháp preview cũ hay `--enable-preview`.

## 1. Vì sao phải kiểm tra tại thời điểm khởi tạo?

Giả sử ta mô hình hóa một dòng hàng:

~~~java
// Mã minh họa (không phải một chương trình độc lập).
record Item(String code, int quantity) {}
~~~

Mọi lệnh sau đều hợp lệ với bản khai báo trên:

~~~java
Item a = new Item(null, 3);
Item b = new Item("   ", 2);
Item c = new Item("ABC", -5);
~~~

Java sinh canonical constructor nhận `String code` và `int quantity`, rồi lưu chúng vào các component fields. Trình biên dịch biết **kiểu** của từng tham số, nhưng không biết quy tắc miền nghiệp vụ như “mã không được trống” hoặc “số lượng phải dương”.

**Bất biến của record** là các điều kiện phải đúng đối với **mọi đối tượng khởi tạo thành công**. Ví dụ:

- `code != null` và `!code.isBlank()` sau bước chuẩn hóa.
- `quantity > 0`.
- `unitPrice != null` và `unitPrice.signum() >= 0` nếu giá bằng 0 được phép.
- `startDate.isBefore(endDate)` đối với một khoảng ngày có độ dài dương.
- Danh sách components không có phần tử `null`/trống và không thể bị sửa từ bên ngoài nếu API muốn dữ liệu bất biến.

Đưa validation vào canonical constructor bảo vệ chính đường khởi tạo thường dùng `new RecordName(...)`, đồng thời giúp mọi constructor bổ sung phải đi qua cùng logic nếu chúng ủy quyền đúng cách. Nếu vi phạm, ném ngoại lệ: đối tượng không được tạo thành công với trạng thái sai.

## 2. Dùng compact canonical constructor để kiểm tra

### 2.1. Cú pháp cơ bản

~~~java
record Quantity(int value) {
    public Quantity {
        if (value <= 0) {
            throw new IllegalArgumentException("value phải dương");
        }
    }
}
~~~

**Đoạn minh họa** này có thể đặt tại cấp tệp (không có `public` trước `record`) hoặc trong phạm vi khai báo kiểu hợp lệ. Với `new Quantity(3)`, kiểm tra vượt qua và đối tượng chứa `3`. Với `new Quantity(0)`, constructor ném `IllegalArgumentException`.

Một **compact canonical constructor** có dạng `public Quantity { ... }`; tên tham số và danh sách tham số được **suy ra từ header của record**. Sau khi body chạy bình thường, trình biên dịch **tự gán** các tham số này vào component fields theo thứ tự đã khai báo.

Không viết:

~~~java
// KHÔNG HỢP LỆ trong compact constructor:
record WrongQuantity(int value) {
    WrongQuantity {
        // this.value = value; // Lỗi biên dịch nếu bỏ comment.
    }
}
~~~

Ở compact constructor, **không được tự gán `this.value`**, và cũng không dùng `return` để kết thúc constructor. Có thể đọc, kiểm tra và **gán lại tham số `value`** trước bước gán ngầm cuối cùng.

> **Phân biệt:** `value` trong body compact constructor là **tham số**; `this.value` là **trường của record**. Trong lúc body đang thực thi, component fields chưa được gán bởi bước khởi tạo ngầm. Hãy kiểm tra các tham số và chỉ dùng chúng để xác định giá trị cần lưu.

### 2.2. Vừa chuẩn hóa vừa kiểm tra

~~~java
import java.util.Locale;
import java.util.Objects;

// Đoạn minh họa; cần đặt import ở đầu tệp nếu dùng nguyên văn.
record ProductCode(String value) {
    public ProductCode {
        value = Objects.requireNonNull(value, "value")
                .strip().toUpperCase(Locale.ROOT);
        if (value.isBlank()) {
            throw new IllegalArgumentException("Mã sản phẩm trống");
        }
    }
}
~~~

Thứ tự rất quan trọng:

1. `Objects.requireNonNull(value, "value")` từ chối tham chiếu `null` trước khi gọi phương thức trên chuỗi.
2. `strip()` bỏ khoảng trắng đầu/cuối theo quy tắc Unicode của Java.
3. `toUpperCase(Locale.ROOT)` tạo mã hoa theo quy tắc không phụ thuộc ngôn ngữ mặc định của máy (chỉ dùng nếu miền nghiệp vụ quy định mã không phân biệt hoa/thường).
4. `isBlank()` kiểm tra **giá trị sau khi chuẩn hóa**.
5. Khi constructor hoàn tất, trình biên dịch lưu **tham số `value` đã được gán lại**, không lưu chuỗi ban đầu.

**Không phải lúc nào cũng được tự chuẩn hóa.** Với mật khẩu, mã định danh phân biệt chữ hoa/thường hoặc chuỗi có khoảng trắng mang nghĩa, tự ý `strip()`/đổi chữ hoa có thể làm sai dữ liệu. Viết rõ chính sách của từng component rồi mới quyết định bước chuẩn hóa.

### 2.3. Normal canonical constructor khi cần gán tường minh

Java cũng cho phép viết constructor đầy đủ với đúng danh sách component:

~~~java
record Range(int start, int end) {
    public Range(int start, int end) {
        if (start > end) {
            throw new IllegalArgumentException("start phải <= end");
        }
        this.start = start;
        this.end = end;
    }
}
~~~

Đây là **normal canonical constructor**: bạn phải tự khởi tạo **tất cả component fields**; chỉ thêm một phần và bỏ quên phần khác sẽ gây lỗi biên dịch.

Hai lựa chọn đều hợp lệ trong Java hiện đại:

| Dạng | Đặc điểm | Thường chọn khi |
|---|---|---|
| `public Range { ... }` | Nhận tham số ngầm định; chỉ cần logic kiểm tra/chuẩn hóa; trình biên dịch tự gán fields | Đa số record cần validate dữ liệu |
| `public Range(int start, int end) { ... }` | Viết tham số đầy đủ; phải tự gán `this.start`, `this.end` | Cần thể hiện rõ logic khởi tạo tường minh |

**Không khai báo cả compact và normal canonical constructor trong cùng một record.** Chúng cùng biểu diễn canonical constructor cho các components đó.

## 3. Những nhóm điều kiện cần kiểm tra

| Loại điều kiện | Ví dụ | Cách kiểm tra phù hợp |
|---|---|---|
| Tham chiếu bắt buộc không được `null` | `code`, `unitPrice`, `tags` | `Objects.requireNonNull(x, "tên")` |
| Chuỗi không được rỗng sau chuẩn hóa | Mã khách hàng | `x = x.strip(); if (x.isBlank()) throw ...` |
| Miền số hợp lệ | `quantity > 0`, `amount >= 0` | So sánh rõ ràng với biên; thông điệp nêu đúng tham số |
| Điều kiện giữa components | `start < end`, `min <= max` | Kiểm tra sau khi từng component bắt buộc đã được kiểm tra `null` |
| Danh sách không có phần tử không hợp lệ | Mỗi tag khác `null` và không blank | Duyệt từng phần tử và báo lỗi; sau đó tạo defensive copy |
| Tập giá trị rời rạc | `status` trong một số trạng thái hợp lệ | Cân nhắc `enum` thay cho chuỗi tự do; nếu nhận chuỗi ngoài hệ thống, parse/validate rõ ràng |
| Số thực có điều kiện hữu hạn | Tọa độ hoặc đo lường không được `NaN`/vô cực | `Double.isFinite(x)` trước khi so sánh ngưỡng |

**Chọn loại ngoại lệ phù hợp:**

- `NullPointerException` qua `Objects.requireNonNull` là lựa chọn Java thông dụng khi tham chiếu bắt buộc bị `null`.
- `IllegalArgumentException` thường phù hợp khi tham số khác `null` nhưng **sai miền giá trị** (số âm, chuỗi trống, thứ tự ngày sai…).
- Có thể chọn quy ước riêng của API; cần **nhất quán** và thông điệp đủ rõ để người gọi sửa dữ liệu. Tránh đưa dữ liệu nhạy cảm như mật khẩu, token vào thông điệp lỗi.

**Chú ý ranh giới:** Quy tắc nghiệp vụ “giá tiền không được âm” không đồng nghĩa “giá luôn lớn hơn 0”; hệ thống có thể có hàng miễn phí. Chọn `< 0` hoặc `<= 0` theo hợp đồng thực tế thay vì copy nguyên ví dụ.

## 4. Kiểm tra nhiều components có quan hệ với nhau

Một record có thể có từng trường hợp lệ nhưng **tổ hợp lại không hợp lệ**. Ví dụ một kỳ đặt lịch cần ngày kết thúc sau ngày bắt đầu:

~~~java
import java.time.LocalDate;
import java.util.Objects;

// Đoạn minh họa; chưa phải chương trình độc lập.
record BookingPeriod(LocalDate start, LocalDate end) {
    public BookingPeriod {
        Objects.requireNonNull(start, "start");
        Objects.requireNonNull(end, "end");
        if (!end.isAfter(start)) {
            throw new IllegalArgumentException(
                    "end phải sau start");
        }
    }
}
~~~

Đây là bất biến **liên component**. Không thể bảo đảm nó chỉ bằng cách thêm kiểm tra `start != null` và `end != null` riêng lẻ.

Khi thêm điều kiện khác, hãy chọn thứ tự kiểm tra hợp lý:

1. Kiểm tra `null`/kiểu/định dạng ở từng component, để tránh lỗi phát sinh tình cờ.
2. Chuẩn hóa nếu đặc tả cho phép, trước khi kiểm tra điều kiện dựa trên dạng đã chuẩn hóa.
3. Kiểm tra miền giá trị cục bộ: ví dụ số lượng dương.
4. Kiểm tra quan hệ giữa các components: ngày bắt đầu/kết thúc, giá trị tối thiểu/tối đa.
5. Chụp bản sao bảo vệ các dữ liệu mutable được giữ lại trong record.

Với hệ thống có yêu cầu *luôn ném lỗi A trước lỗi B*, thứ tự này trở thành một phần hợp đồng API và nên có kiểm thử tương ứng. Với validation đơn giản, ưu tiên thông báo lỗi dễ hiểu và tính nhất quán.

## 5. Kiểm tra dữ liệu tham chiếu mutable: defensive copy

### 5.1. `final` không đồng nghĩa “bất biến sâu”

Record fields là `final`, nhưng bản thân đối tượng được trường tham chiếu đến có thể vẫn thay đổi:

~~~java
// Mã minh họa một cách viết thiếu an toàn khi caller giữ List mutable.
record Tags(List<String> values) {}
~~~

Nếu truyền một `ArrayList` vào `new Tags(list)`, rồi gọi `list.add(...)` sau đó, nội dung của `Tags.values()` cũng thay đổi bởi vì **hai tham chiếu chỉ cùng một danh sách**. Nếu cho phép caller gọi `tags.values().add(...)`, đối tượng còn có thể bị sửa thông qua accessor.

Cách bảo vệ với danh sách chứa các phần tử **bất biến** như `String`:

~~~java
import java.util.List;
import java.util.Objects;

// Mã minh họa.
record Tags(List<String> values) {
    public Tags {
        Objects.requireNonNull(values, "values");
        for (String value : values) {
            if (value == null || value.isBlank()) {
                throw new IllegalArgumentException(
                        "values không được chứa null hoặc chuỗi trống");
            }
        }
        values = List.copyOf(values);
    }
}
~~~

`List.copyOf(values)` lưu **snapshot không thể sửa bằng API của List** và tách dữ liệu khỏi bản `ArrayList` do caller sở hữu. Nếu danh sách đầu vào chứa `null`, `List.copyOf` cũng ném `NullPointerException`; ví dụ kiểm tra trước để thông điệp về lỗi nghiệp vụ rõ ràng hơn.

**Lưu ý giới hạn:** `List.copyOf` chỉ copy **cấu trúc danh sách**, không clone từng phần tử. Nếu phần tử là `String` hoặc kiểu bất biến, đây là lựa chọn tốt. Nếu phần tử là đối tượng mutable, caller vẫn có thể thay đổi trạng thái bên trong phần tử đó; muốn bất biến sâu, cần thiết kế dữ liệu con bất biến hoặc copy phù hợp từng phần tử.

`Collections.unmodifiableList(original)` chỉ tạo **view không cho sửa qua tham chiếu đó**; nếu caller vẫn giữ `original` và chỉnh sửa nó, view có thể phản ánh thay đổi. Vì vậy view không thay thế được defensive copy.

### 5.2. Với mảng hay đối tượng mutable khác

Nếu component là `int[]`, `Date` hay một đối tượng mutable:

- Cần cân nhắc **copy lúc nhập vào** để bảo vệ khỏi thay đổi do caller giữ tham chiếu.
- Có thể phải **copy lúc trả ra từ accessor** để không lộ tham chiếu mutable bên trong.
- Với component dạng mảng, `equals`/`hashCode` do record sinh ra mặc định dùng quy tắc so sánh của mảng qua `equals`/`hashCode` (dựa trên danh tính), **không tự so sánh nội dung phần tử**. Đừng mặc định một record chứa mảng hoạt động như “giá trị bất biến sâu”.

Nếu một dữ liệu được dùng làm record vì cần **value semantics**, ưu tiên các kiểu bất biến (`String`, `BigDecimal`, `LocalDate`, record khác đã bảo vệ bất biến) hoặc các tập hợp đã được copy và có phần tử bất biến.

## 6. Constructor bổ sung không được bỏ qua kiểm tra

Một record có thể có constructor ít tham số hơn để cung cấp **giá trị mặc định hợp lệ**, nhưng nó phải ủy quyền về canonical constructor:

~~~java
import java.math.BigDecimal;
import java.util.List;

// Mã minh họa.
record OrderLine(String sku, int quantity, BigDecimal price, List<String> labels) {
    public OrderLine {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku không hợp lệ");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity phải dương");
        }
        if (price == null || price.signum() < 0) {
            throw new IllegalArgumentException("price không hợp lệ");
        }
        labels = List.copyOf(labels);
    }

    public OrderLine(String sku, int quantity, BigDecimal price) {
        this(sku, quantity, price, List.of());
    }
}
~~~

Trong ví dụ, `new OrderLine("SKU", 0, BigDecimal.ONE)` vẫn ném ngoại lệ vì constructor ba tham số gọi constructor bốn tham số có validation. Một constructor bổ sung **không được tạo đường vòng để tạo record sai invariant**.

**Trong Java 17**, constructor record bổ sung dùng `this(...)` để chuyển sang canonical constructor theo quy tắc constructor chaining. Không nên cố tạo logic gán trực tiếp các component fields để tránh gọi constructor chính.

Static factory như `OrderLine.of(...)` cũng có thể hỗ trợ parse/chuẩn hóa dữ liệu đến từ API; nhưng factory **không thay thế validation canonical constructor** nếu code bên ngoài vẫn có thể gọi `new OrderLine(...)`. Một cách thiết kế nhất quán là factory tạo ra giá trị, còn canonical constructor vẫn giữ bất biến tối thiểu của đối tượng.

## 7. Chương trình Java 17+ đầy đủ: kiểm tra, chuẩn hóa, chống sửa dữ liệu

Tạo tệp **`RecordInputValidationDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class RecordInputValidationDemo {
    record Item(String code, int quantity, BigDecimal unitPrice, List<String> tags) {
        public Item {
            code = Objects.requireNonNull(code, "code")
                    .strip().toUpperCase(Locale.ROOT);
            if (code.isBlank()) {
                throw new IllegalArgumentException("code trống");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity phải dương");
            }
            Objects.requireNonNull(unitPrice, "unitPrice");
            if (unitPrice.signum() < 0) {
                throw new IllegalArgumentException("unitPrice không được âm");
            }
            Objects.requireNonNull(tags, "tags");
            for (String tag : tags) {
                if (tag == null || tag.isBlank()) {
                    throw new IllegalArgumentException("tags có phần tử trống");
                }
            }
            tags = List.copyOf(tags);
        }

        public Item(String code, int quantity, BigDecimal unitPrice) {
            this(code, quantity, unitPrice, List.of());
        }

        public BigDecimal amount() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    public static void main(String[] args) {
        List<String> editable = new ArrayList<>(List.of("fragile"));
        Item ok = new Item(" ab-01 ", 2, new BigDecimal("12.50"), editable);
        System.out.println("code=" + ok.code());
        System.out.println("amount=" + ok.amount().toPlainString());

        editable.add("late");
        System.out.println("tags=" + ok.tags());
        try {
            ok.tags().add("extra");
        } catch (UnsupportedOperationException e) {
            System.out.println("readonly=true");
        }
        try {
            new Item("  ", 1, BigDecimal.ONE);
        } catch (IllegalArgumentException e) {
            System.out.println("invalidCode=" + e.getMessage());
        }
        try {
            new Item("X", 0, BigDecimal.ONE);
        } catch (IllegalArgumentException e) {
            System.out.println("invalidQuantity=" + e.getMessage());
        }
        try {
            new Item("X", 1, BigDecimal.valueOf(-2));
        } catch (IllegalArgumentException e) {
            System.out.println("invalidPrice=" + e.getMessage());
        }
        try {
            new Item("X", 1, BigDecimal.ONE, Arrays.asList("ok", null));
        } catch (IllegalArgumentException e) {
            System.out.println("invalidTag=" + e.getMessage());
        }
        try {
            new Item(null, 1, BigDecimal.ONE);
        } catch (NullPointerException e) {
            System.out.println("nullCode=" + e.getMessage());
        }
        System.out.println("overload=" + new Item("X", 1, BigDecimal.ONE).tags());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 RecordInputValidationDemo.java
java RecordInputValidationDemo
~~~

**Đầu ra đã kiểm tra khi biên dịch/chạy:**

~~~text
code=AB-01
amount=25.00
tags=[fragile]
readonly=true
invalidCode=code trống
invalidQuantity=quantity phải dương
invalidPrice=unitPrice không được âm
invalidTag=tags có phần tử trống
nullCode=code
overload=[]
~~~

**Diễn giải:**

1. `" ab-01 "` thành `"AB-01"` vì compact constructor gán lại tham số `code` trước khi compiler tự lưu trường.
2. `quantity = 2` và `unitPrice = 12.50` hợp lệ; `BigDecimal` nhân ra `25.00`, dùng `toPlainString()` để in đúng giá trị.
3. `editable.add("late")` thay đổi danh sách gốc, **không** làm thay đổi `ok.tags()`; record đã lưu bản sao.
4. `ok.tags().add("extra")` ném `UnsupportedOperationException` vì danh sách lưu trong record là unmodifiable.
5. Mã trống, số lượng bằng 0, giá âm và tag `null` bị từ chối bởi các điều kiện rõ ràng trong compact constructor.
6. `code == null` bị `Objects.requireNonNull` từ chối; thông điệp `"code"` được in ra trong `catch (NullPointerException e)`.
7. Constructor ba tham số đi qua canonical constructor nên mặc định `List.of()` và vẫn giữ toàn bộ validation.

**Kết quả bất biến sau khởi tạo:** mọi `Item` tạo thành công có `code` khác null và không blank, `quantity > 0`, `unitPrice >= 0`, danh sách tag không có null/blank và không thể bị thay đổi qua danh sách gốc hoặc accessor. Trong ví dụ này phần tử `String` là bất biến; vì vậy không phát sinh vấn đề mutable element.

## 8. Kiểm tra những đường đi quan trọng

Đừng chỉ thử một đầu vào hợp lệ. Nên thử cả **giá trị biên**, dữ liệu không hợp lệ và trường hợp có thể phá invariant sau khi constructor trả về.

| Nhóm | Đầu vào thử | Kết quả mong đợi |
|---|---|---|
| Hợp lệ | `code="A"`, `quantity=1`, `unitPrice=BigDecimal.ZERO` | Khởi tạo thành công nếu giá 0 hợp lệ theo chính sách |
| Thiếu mã | `code=null` | Từ chối rõ ràng (ví dụ NPE với tên component) |
| Mã chỉ có khoảng trắng | `code="   "` | Từ chối sau khi chuẩn hóa |
| Biên số lượng | `quantity=0`, `quantity=-1` | `IllegalArgumentException` |
| Biên giá | `unitPrice=-0.01`, `unitPrice=0` | Số âm bị từ chối, 0 được chấp nhận theo ví dụ |
| Sai quan hệ | `start=end` khi yêu cầu `start<end` | Từ chối |
| Danh sách có `null` | `tags=["ok", null]` | Từ chối với lý do cụ thể |
| Danh sách mutable | Sửa `ArrayList` gốc sau khi tạo record | Component không bị sửa theo |
| Sửa qua accessor | Gọi `record.tags().add(...)` | Không cho sửa danh sách đã copy |
| Constructor bổ sung | Dùng overload với `quantity=0` | Validation canonical vẫn chạy |

**Thiết kế test tốt:** kiểm tra cả **loại ngoại lệ** và **giá trị được chuẩn hóa**; nếu có defensive copy, kiểm tra cả hai hướng: sửa **đầu vào gốc** và sửa **đối tượng trả từ accessor**. Với JUnit, có thể dùng `assertThrows(...)`, nhưng chương trình ở phần 7 không cần thư viện kiểm thử ngoài JDK.

Nếu record chứa số thực `double`/`float` với invariant số hữu hạn, phải thử thêm `Double.NaN`, `Double.POSITIVE_INFINITY` và `Double.NEGATIVE_INFINITY`. Ví dụ điều kiện `x < 0` **không bắt được NaN**, vì so sánh với NaN trả `false`; dùng `Double.isFinite(x)` khi cần loại cả NaN và vô cực.

## 9. Những lỗi phổ biến

### Lỗi 1: Tin rằng `record` tự validate business rule

~~~java
// Chỉ định nghĩa kiểu dữ liệu, không kiểm tra quantity.
record SimpleItem(int quantity) {}
~~~

`new SimpleItem(-2)` vẫn tạo thành công. Cần khai báo canonical/compact constructor với quy tắc domain.

### Lỗi 2: Gán trực tiếp component field trong compact constructor

Viết `this.code = code;` trong body `public Item { ... }` gây **lỗi biên dịch**. Tham số có thể được gán lại như `code = code.strip();`; trình biên dịch thực hiện bước lưu field sau body.

### Lỗi 3: Gọi phương thức trên `null` trước khi kiểm tra

`code.strip()` với `code == null` ném NPE khó truy vết nếu không có thông điệp. Dùng `Objects.requireNonNull(code, "code")` hoặc kiểm tra tham số trước rồi mới chuẩn hóa.

### Lỗi 4: Kiểm tra sai ranh giới hoặc sai thứ tự

Nếu yêu cầu `quantity > 0` thì điều kiện từ chối là `quantity <= 0`. Nếu yêu cầu khoảng ngày **có ít nhất một ngày**, `end.isAfter(start)` khác với `!end.isBefore(start)` (cho phép bằng nhau). Biên phải phản ánh đặc tả miền nghiệp vụ.

### Lỗi 5: Chỉ dùng `Collections.unmodifiableList(original)`

View có thể vẫn thay đổi khi caller chỉnh sửa `original`. Dùng `List.copyOf(original)` để lưu snapshot khi phần tử bên trong bất biến; nếu phần tử mutable, cần chiến lược copy sâu hoặc kiểu dữ liệu khác.

### Lỗi 6: Chỉ validate ở factory/controller/annotation

Nếu yêu cầu invariant luôn đúng đối với mọi đối tượng được tạo bằng public canonical constructor, validation ở factory hoặc controller **không đủ**, vì code khác có thể gọi `new` trực tiếp.

Các annotation như `@NotNull`, `@NotBlank` theo Jakarta Bean Validation **không tự kích hoạt chỉ vì gọi `new SomeRecord(...)`**; cần có cơ chế validator/framework thực sự chạy chúng. Có thể dùng Bean Validation ở ranh giới HTTP/API như lớp bổ sung, còn các bất biến căn bản vẫn nên được thực thi trong constructor nếu cần đảm bảo cho mọi đường tạo record.

### Lỗi 7: Chuẩn hóa làm mất thông tin hoặc làm thay đổi hợp đồng

Không `toUpperCase` mật khẩu, không tự cắt khoảng trắng của chuỗi mà khoảng trắng là dữ liệu, không xóa phần tử sai để “biến thành dữ liệu hợp lệ” nếu hệ thống phải trả lỗi. Chuẩn hóa phải được đặc tả, nhất quán và **idempotent** khi có thể: đưa giá trị đã chuẩn hóa qua constructor lần nữa sẽ có ý nghĩa tương đương.

### Lỗi 8: Nhầm bất biến của tham chiếu với bất biến của đối tượng

`private final List<T>` không ngăn phần tử mutable thay đổi; `private final int[]` cũng không ngăn sửa phần tử mảng. Kiểm tra hợp lệ tại lúc tạo chỉ giữ được tác dụng dài hạn nếu dữ liệu bên trong không bị sửa theo con đường khác.

## 10. Quy trình thiết kế validation cho một record mới

1. **Đặt tên invariant**: mỗi component phải thỏa điều kiện gì, cặp/tập components phải thỏa quan hệ gì?
2. **Chọn kiểu dữ liệu** phù hợp: `int` cho đếm, `BigDecimal` cho giá, `LocalDate` cho ngày, `enum` cho trạng thái đóng; giảm dữ liệu tự do khó kiểm chứng.
3. **Định nghĩa chính sách null và giá trị biên**: chấp nhận `0` không? chuỗi rỗng có nghĩa không? danh sách null là lỗi hay được thay bằng danh sách rỗng?
4. **Quyết định chuẩn hóa**: có `strip`/đổi hoa thường/giảm độ chính xác? Lỗi phải được báo hay tự sửa? Chọn một chính sách rõ.
5. **Đặt validation trong canonical/compact constructor** nếu invariant phải đúng với mọi đối tượng được khởi tạo thành công.
6. **Chụp bản sao** cho dữ liệu mutable sau kiểm tra, cân nhắc liệu cần copy sâu và bảo vệ accessor hay không.
7. **Cho các constructor phụ ủy quyền vào canonical constructor**; không tạo đường vòng bỏ qua điều kiện.
8. **Kiểm tra cả happy path, boundary, negative path và mutation path**. Chạy lại khi quy tắc nghiệp vụ thay đổi.

## 11. Tự luyện tập

**Bài 1.** Viết record `Age(int value)` chỉ chấp nhận tuổi trong khoảng 0–120, bao gồm hai đầu mút.

*Gợi ý/đáp án:* Trong `public Age { ... }`, ném `IllegalArgumentException` nếu `value < 0 || value > 120`. Kiểm tra thêm `-1`, `0`, `120`, `121`.

**Bài 2.** Với `record Period(LocalDate start, LocalDate end)`, điều kiện nào phải kiểm tra nếu `end` phải sau `start` ít nhất một ngày?

*Đáp án:* Kiểm tra cả hai giá trị không null, rồi từ chối khi `!end.isAfter(start)`. Nếu nghiệp vụ cho phép ngày bằng nhau, phải thay điều kiện.

**Bài 3.** Một record nhận `List<String> labels`; sau khi tạo, caller thay đổi danh sách gốc. Chỉ khai báo component là `List<String>` có đủ không?

*Đáp án:* Không. Component field là `final` nhưng danh sách vẫn mutable. Kiểm tra từng phần tử rồi lưu `List.copyOf(labels)` (giả sử phần tử `String` bất biến). Việc gọi `Collections.unmodifiableList(labels)` đơn thuần tạo view và không ngăn sửa qua danh sách gốc.

**Bài 4.** Trong `public ProductCode { value = value.strip(); }`, tham số `value` có được sửa không, và có cần `this.value = value` không?

*Đáp án:* Có thể gán lại tham số `value`. Không được gán component field trực tiếp trong compact constructor; compiler tự làm việc đó sau body.

**Bài 5.** Nếu thêm overload `Item(String code, int quantity, BigDecimal price)` thì làm sao đảm bảo kiểm tra giống overload đủ bốn tham số?

*Đáp án:* Gọi `this(code, quantity, price, List.of())`; mọi đường khởi tạo sẽ đi qua canonical constructor có kiểm tra.

## Tài liệu đối chiếu

- [JEP 395 — Records](https://openjdk.org/jeps/395): records chính thức ở Java 16, mục đích dữ liệu dạng value carrier và compact constructors.
- [Oracle Java 17 — Record Classes](https://docs.oracle.com/en/java/javase/17/language/records.html): normal/compact canonical constructors, kiểm tra dữ liệu, giới hạn field và cách khởi tạo.
- [Java Language Specification SE 17 — `8.10 Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): các thành phần/fields/constructors của record.
- [Java Language Specification SE 17 — `8.10.4 Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4): quy tắc chính xác cho canonical và compact constructors.
- [Dev.java — Using Records to Model Immutable Data](https://dev.java/learn/using-record-to-model-immutable-data/): defensive copy, getter và constructor bổ sung.
- [Java SE 17 API — `List.copyOf`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): bản sao unmodifiable và quy tắc null.
- [Java SE 17 API — `Objects.requireNonNull`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T,java.lang.String)): kiểm tra tham chiếu bắt buộc.

**Ghi nhớ:** Record giúp giảm mã lặp khi định nghĩa dữ liệu, còn **validation là trách nhiệm của thiết kế**. Hãy bảo vệ các bất biến ngay trong canonical constructor, chuẩn hóa có chủ đích, chụp bản sao với dữ liệu mutable và kiểm tra cả trường hợp sai để mọi đối tượng tạo thành công đều mang dữ liệu có ý nghĩa.