# Tính đầy đủ, `default` và `switch` trên `enum` trong Java 17

## 1. Vì sao tính đầy đủ quan trọng với `switch expression`?

Trong Java 17, **switch expression** là một biểu thức tạo ra giá trị. Bạn có thể dùng nó ở vế phải của phép gán, trả về trực tiếp từ phương thức hoặc truyền vào một biểu thức khác. Khác với một câu lệnh `switch` thông thường chỉ điều khiển luồng thực thi, `switch expression` phải xác định được kết quả trên **mọi giá trị hợp lệ** của biểu thức chọn (*selector*).

Ví dụ đơn giản với một `enum` trạng thái đơn hàng:

~~~java
enum OrderStatus {
    CREATED, PAID, SHIPPED, DELIVERED, CANCELLED
}

static String displayName(OrderStatus status) {
    return switch (status) {
        case CREATED -> "Created";
        case PAID -> "Paid";
        case SHIPPED -> "Shipped";
        case DELIVERED -> "Delivered";
        case CANCELLED -> "Cancelled";
    };
}
~~~

Đoạn mã này **không có `default`** nhưng vẫn hợp lệ trong Java 17. Lý do: năm nhánh `case` đã bao phủ **toàn bộ năm hằng của `OrderStatus`** mà trình biên dịch biết đến. Java gọi tính chất này là **exhaustiveness** — *tính đầy đủ của các nhánh*.

Ngược lại, nếu thiếu `CANCELLED`, trình biên dịch không thể bảo đảm `switch` trả ra một chuỗi cho giá trị đó:

~~~java
// Ví dụ cố ý KHÔNG biên dịch: thiếu CANCELLED
static String incomplete(OrderStatus status) {
    return switch (status) {
        case CREATED -> "Created";
        case PAID -> "Paid";
        case SHIPPED -> "Shipped";
        case DELIVERED -> "Delivered";
    };
}
~~~

Đây là **lỗi biên dịch** vì `switch expression` chưa bao phủ hết hằng của `enum` và cũng không có `default` để xử lý phần còn lại. Đó là cơ chế bảo vệ rất hữu ích khi các trạng thái nghiệp vụ được mô hình hóa bằng `enum`.

> **Quy tắc cốt lõi trong Java 17:** Một `switch expression` bắt buộc phải đầy đủ. Với selector có kiểu `enum`, bạn có thể đạt tính đầy đủ bằng cách liệt kê tất cả hằng `enum`, hoặc thêm nhánh `default` để xử lý các giá trị chưa được liệt kê.

### Mục tiêu học tập

Sau bài này, bạn sẽ:

- Nhận biết khi nào `switch expression` được coi là đầy đủ và vì sao thiếu nhánh dẫn tới lỗi biên dịch.
- Hiểu vai trò của `default` và vì sao **không phải lúc nào cũng nên viết `default`** khi chuyển đổi mọi hằng `enum`.
- Sử dụng `switch` với `enum`, gom nhiều hằng vào một nhánh, trả giá trị bằng `->` và `yield`.
- Dự đoán ảnh hưởng khi một `enum` được bổ sung hằng mới.
- Phân biệt `default` với việc xử lý `null`; biết cách xác định chính sách khi selector có thể bằng `null`.
- Tổ chức ví dụ Java 17 thực tế, chạy bằng `javac` và `java` mà không cần tính năng preview.

## 2. Phân biệt `switch statement` và `switch expression`

Hai dạng `switch` dễ bị nhầm vì có vẻ giống nhau:

### 2.1. `switch statement`: thực thi hành động

~~~java
static void logStatus(OrderStatus status) {
    switch (status) {
        case CREATED:
            System.out.println("Order created");
            break;
        case PAID:
            System.out.println("Payment received");
            break;
        default:
            System.out.println("Other status");
    }
}
~~~

`switch` truyền thống ở đây là **câu lệnh**, không trả giá trị. Trường hợp không có nhánh phù hợp, chương trình có thể đơn giản tiếp tục sau câu lệnh `switch`. Các nhánh dùng dấu `:`, và `break` giúp tránh *fall-through* ngoài ý muốn.

### 2.2. `switch expression`: tính ra một giá trị

~~~java
static String statusCategory(OrderStatus status) {
    return switch (status) {
        case CREATED, PAID -> "OPEN";
        case SHIPPED, DELIVERED -> "FULFILLMENT";
        case CANCELLED -> "CLOSED";
    };
}
~~~

Ở đây:

1. Từ khóa `switch` là một **biểu thức** nằm sau `return`.
2. Ký hiệu `->` đưa chương trình tới đúng nhánh mà không chạy xuyên sang nhánh khác.
3. Giá trị của nhánh được dùng làm giá trị chung của toàn biểu thức.
4. Mỗi hằng `enum` xuất hiện đúng một lần, đủ để bỏ `default`.

| Tiêu chí | `switch statement` truyền thống | `switch expression` |
|---|---|---|
| Mục đích | Chọn các câu lệnh để thực thi. | Tạo một giá trị hoặc ném ngoại lệ. |
| Có bắt buộc đầy đủ? | Không bắt buộc với câu lệnh `switch` truyền thống. | **Có**, trình biên dịch kiểm tra tính đầy đủ. |
| Cú pháp nhánh | Thường dùng `case X:` và `break`; Java 17 cũng hỗ trợ switch rule với `->`. | Thường dùng `case X -> value` hoặc block với `yield`. |
| Giá trị trả về | Không có giá trị của bản thân câu lệnh. | Có một giá trị có kiểu phù hợp với ngữ cảnh. |
| Bỏ `default` khi bao phủ đủ `enum` | Có thể; nhưng câu lệnh vẫn không trả giá trị. | **Có thể** và thường có lợi cho việc theo dõi các hằng mới. |

Đừng nhầm `break` của câu lệnh `switch` truyền thống với `yield` của `switch expression`: `break` thoát một câu lệnh; `yield` cung cấp giá trị cho biểu thức.

## 3. Quy tắc tính đầy đủ khi selector là `enum`

Với một biến có kiểu tĩnh `OrderStatus`:

~~~java
OrderStatus status = OrderStatus.PAID;
~~~

Java biết các hằng enum được khai báo trong mã nguồn hoặc trong tệp lớp mà nó biên dịch dựa vào:

~~~text
OrderStatus
├── CREATED
├── PAID
├── SHIPPED
├── DELIVERED
└── CANCELLED
~~~

Vì thế, có ít nhất hai chiến lược tạo `switch expression` đầy đủ:

**Cách A — Liệt kê toàn bộ hằng:**

~~~java
return switch (status) {
    case CREATED -> "New";
    case PAID -> "Paid";
    case SHIPPED -> "On the way";
    case DELIVERED -> "Finished";
    case CANCELLED -> "Stopped";
};
~~~

**Cách B — Liệt kê một số hằng, để `default` xử lý phần còn lại:**

~~~java
return switch (status) {
    case CREATED, PAID -> "ACTIVE";
    default -> "OTHER";
};
~~~

Cả hai đều thỏa tính đầy đủ, nhưng **ý nghĩa bảo trì khác nhau**. Cách A thể hiện rõ cách xử lý từng hằng; cách B cho phép các hằng không được nêu tên cùng vào một nhánh.

### Gom nhiều hằng trong một `case`

Không nhất thiết mỗi hằng phải có một biểu thức kết quả khác nhau:

~~~java
static boolean canCancel(OrderStatus status) {
    return switch (status) {
        case CREATED, PAID -> true;
        case SHIPPED, DELIVERED, CANCELLED -> false;
    };
}
~~~

Việc nhóm `CREATED, PAID` và `SHIPPED, DELIVERED, CANCELLED` vẫn bao phủ đầy đủ năm hằng. Đây là cách thuận tiện khi nhiều giá trị có cùng hành vi, đồng thời vẫn **liệt kê rõ** những hằng thuộc mỗi nhóm.

### Những điều kiện không thay thế được tính đầy đủ

- Một nhánh `case` được viết rất phức tạp không tự động làm `switch` đầy đủ.
- Việc biết rằng dữ liệu ở **thực tế** "chỉ có CREATED hoặc PAID" không đủ để biên dịch một `switch expression` thiếu các hằng khác của cùng `enum`. Trình biên dịch dựa trên kiểu selector và các nhánh có trong mã, không suy ra các giả định nghiệp vụ bên ngoài.
- Nhánh `default` làm biểu thức đầy đủ về cú pháp, nhưng **không chứng minh kết quả nghiệp vụ đúng** cho mọi hằng bị gom vào.
- Các hằng có mặt trong `enum` mà không có bất kỳ nhánh xử lý nào, nếu không có `default`, sẽ khiến `switch expression` bị từ chối ngay khi biên dịch.

## 4. `default`: khi nào cần và khi nào nên cân nhắc tránh?

### 4.1. `default` giúp xử lý phần chưa liệt kê

Trong nhiều trường hợp, bạn chỉ quan tâm một vài giá trị đặc biệt, còn những giá trị khác có cùng hành vi. Ví dụ:

~~~java
static boolean requiresPayment(OrderStatus status) {
    return switch (status) {
        case CREATED -> true;
        default -> false;
    };
}
~~~

Nếu chính sách nghiệp vụ là **chỉ CREATED cần thanh toán, tất cả trạng thái khác đều không cần**, `default` diễn đạt quy tắc ngắn gọn và rõ ràng. Nó bao phủ `PAID`, `SHIPPED`, `DELIVERED` và `CANCELLED`.

Tương tự, khi selector là `int` hoặc `String`, số giá trị có thể có không hữu hạn nhỏ như `enum`; thông thường bạn sẽ cần `default` để `switch expression` đầy đủ:

~~~java
static String categoryForCode(int code) {
    return switch (code) {
        case 200 -> "SUCCESS";
        case 404 -> "NOT_FOUND";
        default -> "OTHER";
    };
}
~~~

### 4.2. `default` có thể che khuất một trạng thái mới

Giả sử lúc đầu có:

~~~java
enum OrderStatus {
    CREATED, PAID, SHIPPED, DELIVERED, CANCELLED
}
~~~

Một hàm phân loại viết:

~~~java
static String lifecycleGroup(OrderStatus status) {
    return switch (status) {
        case CREATED, PAID -> "BEFORE_SHIPMENT";
        case SHIPPED, DELIVERED -> "AFTER_SHIPMENT";
        default -> "STOPPED";
    };
}
~~~

Khi chỉ có năm hằng trên, `default` đang bắt `CANCELLED`. Sau này, nhóm phát triển bổ sung `RETURNED`:

~~~java
enum OrderStatus {
    CREATED, PAID, SHIPPED, DELIVERED, CANCELLED, RETURNED
}
~~~

Mã `lifecycleGroup` **vẫn có thể biên dịch** vì `default` đã xử lý tất cả giá trị không nêu tên, trong đó có `RETURNED`. Nhưng kết quả `"STOPPED"` cho `RETURNED` có phù hợp hay không lại là câu hỏi nghiệp vụ cần xem xét. Trình biên dịch không thể thay bạn đưa ra quyết định này.

Nếu ngay từ đầu viết rõ mọi hằng:

~~~java
static String lifecycleGroup(OrderStatus status) {
    return switch (status) {
        case CREATED, PAID -> "BEFORE_SHIPMENT";
        case SHIPPED, DELIVERED -> "AFTER_SHIPMENT";
        case CANCELLED -> "STOPPED";
    };
}
~~~

thì sau khi thêm `RETURNED` và **biên dịch lại mã sử dụng enum mới**, biểu thức thiếu nhánh `RETURNED` sẽ **bị báo lỗi biên dịch**. Người phát triển phải quyết định rõ hằng mới thuộc nhóm nào.

Đây là một trong những lợi ích lớn nhất của việc bỏ `default` khi bạn muốn kiểm soát đầy đủ từng hằng `enum`.

### 4.3. Chọn `default` theo ý nghĩa thật của bài toán

| Bối cảnh | Cách viết thường phù hợp | Vì sao? |
|---|---|---|
| Ánh xạ **mỗi** trạng thái enum sang hành vi nghiệp vụ riêng | Liệt kê tất cả hằng, không có `default`. | Khi thêm trạng thái, biên dịch lại sẽ buộc xem xét nhánh mới. |
| Một hoặc vài trạng thái đặc biệt, **mọi** trạng thái khác thật sự có hành vi giống nhau | Dùng `default` có chủ đích. | Thể hiện một chính sách "mọi trường hợp còn lại". |
| Selector là `int`/`String`, không thể liệt kê tất cả giá trị | Thường cần `default`. | Làm biểu thức đầy đủ. |
| Muốn nhận diện giá trị ngoài mong đợi | `default -> throw ...` có thể hợp lý. | Tránh âm thầm trả giá trị giả định, nhưng khi enum mở rộng vẫn cần chủ động rà soát. |

Khi thiết kế API được dùng lâu dài, hãy ưu tiên làm rõ **bất biến nghiệp vụ** trước khi chọn `default` chỉ vì ít dòng hơn.

## 5. `default -> throw`: xử lý lỗi không phải trả giá trị

Trong `switch expression`, một nhánh có thể **ném ngoại lệ** thay vì tạo ra giá trị. Ví dụ:

~~~java
static String shippingCode(OrderStatus status) {
    return switch (status) {
        case SHIPPED -> "IN_TRANSIT";
        case DELIVERED -> "RECEIVED";
        default -> throw new IllegalStateException(
                "Order is not in shipping phase: " + status);
    };
}
~~~

Khi `status == OrderStatus.PAID`, nhánh `default` ném `IllegalStateException`. Lời gọi hàm không trả về một chuỗi; đó là hành vi **có chủ đích** vì phương thức này chỉ hợp lệ với trạng thái vận chuyển.

Tuy vậy, cần phân biệt:

1. `default -> throw` khiến `switch expression` đầy đủ về mặt cú pháp.
2. Nó **không tạo cảnh báo biên dịch** khi enum được bổ sung một hằng mới; hằng mới sẽ rơi vào `default` khi chạy.
3. Nó là một cách thể hiện tiền điều kiện hoặc nhánh phòng vệ, chứ không thay thế việc cập nhật logic nếu hằng mới cần hành vi riêng.

Trong các miền mà **mọi** hằng đều phải được xử lý ở mức nghiệp vụ, liệt kê đầy đủ và không dùng `default` thường dễ theo dõi thay đổi hơn.

## 6. `->`, khối lệnh và `yield` trong `switch expression`

Với một nhánh đơn giản, cú pháp `->` rất gọn:

~~~java
String name = switch (status) {
    case CREATED -> "Created";
    case PAID -> "Paid";
    case SHIPPED -> "Shipped";
    case DELIVERED -> "Delivered";
    case CANCELLED -> "Cancelled";
};
~~~

Nếu một nhánh phải thực hiện nhiều câu lệnh trước khi tính ra kết quả, dùng khối `{ ... }` và **`yield`**:

~~~java
static int priority(OrderStatus status) {
    return switch (status) {
        case CREATED -> 10;
        case PAID -> 20;
        case SHIPPED -> {
            int shippingPriority = 30;
            int trackingBonus = 5;
            yield shippingPriority + trackingBonus;
        }
        case DELIVERED, CANCELLED -> 0;
    };
}
~~~

Ở nhánh `SHIPPED`, `yield shippingPriority + trackingBonus;` trả giá trị `35` cho toàn bộ biểu thức. Các nhánh còn lại có cú pháp ngắn `-> 10`, `-> 20` và `-> 0`.

Những điểm cần nhớ:

- `yield` cung cấp giá trị cho **switch expression** đang bao quanh.
- `yield` không có vai trò tương đương `break` của câu lệnh `switch`.
- Nhánh dạng `case X -> { ... }` không được bỏ mặc một đường đi kết thúc bình thường mà không `yield` hoặc ném ngoại lệ; biểu thức cần được xác định kết quả.
- Các giá trị từ các nhánh phải tương thích để biểu thức có một kiểu kết quả dùng được tại vị trí gọi.
- Các nhánh `->` không bị *fall-through* như khi quên `break` ở cú pháp dấu hai chấm truyền thống.

### Cú pháp dấu hai chấm kết hợp `yield`

`switch expression` cũng có thể dùng dạng nhãn `case X:` cùng `yield`:

~~~java
static String labelWithColon(OrderStatus status) {
    return switch (status) {
        case CREATED:
            yield "Created";
        case PAID:
            yield "Paid";
        case SHIPPED:
            yield "Shipped";
        case DELIVERED:
            yield "Delivered";
        case CANCELLED:
            yield "Cancelled";
    };
}
~~~

Đoạn này vẫn đầy đủ, nhưng thường dài hơn các nhánh `->`. Nếu không có lý do đặc biệt, quy ước `case X -> value` giúp biểu thức ánh xạ enum dễ đọc.

## 7. `null`: trường hợp `default` không tự bắt

Một câu hỏi phổ biến: *"Tôi đã có `default`, vậy nếu enum bằng `null` thì có vào `default` không?"*

**Không.** Với `switch` thông thường trong Java 17, nếu biểu thức selector là tham chiếu `null`, chương trình ném **`NullPointerException`**. Nó không tự nhảy vào nhánh `default`. Chẳng hạn:

~~~java
static String labelWithDefault(OrderStatus status) {
    return switch (status) {
        case CREATED -> "Created";
        default -> "Other";
    };
}

// labelWithDefault(null) -> NullPointerException
~~~

`default` là nhánh cho các **giá trị enum không được liệt kê** trong các `case` trước, chứ không phải cơ chế thay thế kiểm tra tham chiếu `null`.

Đây là hành vi của Java 17 khi dùng `switch` ổn định. Pattern matching cho `switch` có cú pháp mở rộng trong các phiên bản Java khác, nhưng ở Java 17 nó thuộc preview feature; bài này không sử dụng `case null` hoặc yêu cầu bật preview.

### 7.1. Chính sách A: từ chối `null` rõ ràng

Nếu `null` là đầu vào không hợp lệ, hãy kiểm tra ngay tại ranh giới hàm:

~~~java
import java.util.Objects;

static String requireLabel(OrderStatus status) {
    Objects.requireNonNull(status, "status");

    return switch (status) {
        case CREATED -> "Created";
        case PAID -> "Paid";
        case SHIPPED -> "Shipped";
        case DELIVERED -> "Delivered";
        case CANCELLED -> "Cancelled";
    };
}
~~~

`Objects.requireNonNull(status, "status")` vẫn ném `NullPointerException` nếu tham số thiếu, nhưng thông báo chỉ rõ tên tham số. Nó cũng khiến hợp đồng hàm dễ nhận biết hơn khi đọc mã.

### 7.2. Chính sách B: xử lý `null` trước `switch`

Nếu thực sự cần xem thiếu trạng thái là một trường hợp dữ liệu có thể chấp nhận:

~~~java
static String optionalLabel(OrderStatus status) {
    if (status == null) {
        return "Missing status";
    }

    return switch (status) {
        case CREATED -> "Created";
        case PAID -> "Paid";
        case SHIPPED -> "Shipped";
        case DELIVERED -> "Delivered";
        case CANCELLED -> "Cancelled";
    };
}
~~~

Cách này xử lý `null` riêng, sau đó dùng `switch` để xử lý đầy đủ **các hằng thực sự của enum**. Đây là ranh giới rõ ràng giữa sự vắng mặt của tham chiếu và một trạng thái nghiệp vụ.

### 7.3. Có nên thêm hằng `UNKNOWN` vào enum?

Nếu nghiệp vụ có một trạng thái "chưa xác định" hợp lệ, bạn có thể mô hình hóa nó bằng hằng `UNKNOWN`:

~~~java
enum State {
    UNKNOWN, READY, DONE
}
~~~

Khi đó `UNKNOWN` là **một giá trị enum thực sự**, có thể xuất hiện trong `case UNKNOWN`. Tuy nhiên, `null` vẫn là một tham chiếu không trỏ tới đối tượng enum nào; bổ sung `UNKNOWN` **không làm `switch(null)` tự động thành `switch(UNKNOWN)`**. Hãy quyết định chuyển `null` thành `UNKNOWN` (nếu thích hợp) ở lớp xử lý đầu vào.

## 8. Khi enum thêm hằng mới: biên dịch lại và tương thích nhị phân

Giả sử một phương thức đã được biên dịch với enum ban đầu:

~~~java
enum Status {
    NEW, ACTIVE, CLOSED
}

static String title(Status status) {
    return switch (status) {
        case NEW -> "New";
        case ACTIVE -> "Active";
        case CLOSED -> "Closed";
    };
}
~~~

Sau này, enum có thêm `SUSPENDED`:

~~~java
enum Status {
    NEW, ACTIVE, CLOSED, SUSPENDED
}
~~~

Cần phân biệt **hai tình huống**:

### 8.1. Biên dịch lại toàn bộ mã với enum mới

Nếu bạn biên dịch lại cả `title` với phiên bản `Status` đã có `SUSPENDED`, switch expression **thiếu nhánh** và không có `default` sẽ báo lỗi biên dịch. Đây là phản hồi sớm rất có giá trị: người phát triển bắt buộc phải quyết định cách xử lý `SUSPENDED`.

### 8.2. Chỉ thay bytecode enum mới, vẫn chạy mã đã biên dịch cũ

Trong môi trường chia sẻ thư viện, có thể tồn tại mã gọi `switch expression` được biên dịch trước khi enum thêm hằng. Nếu chương trình chạy với **bản enum mới** nhưng giữ **bản switch cũ**, một giá trị mới như `SUSPENDED` có thể đi vào nhánh bảo vệ do trình biên dịch tạo ra cho switch expression trên enum đã được coi là đầy đủ lúc biên dịch. Trên Java 17, trường hợp này có thể dẫn tới **`IncompatibleClassChangeError`**.

Không nên dựa vào việc "không có `default` thì runtime sẽ luôn tự xử lý giá trị mới". **Đảm bảo mạnh nhất là tại thời điểm biên dịch lại**; khi phân phối module/thư viện có thể thay đổi độc lập, cần kiểm soát version, tương thích nhị phân và chạy kiểm thử tích hợp với các phiên bản thực tế.

### 8.3. Nếu có `default` khi thêm hằng mới?

Khi enum mới bổ sung `SUSPENDED`, switch có `default` vẫn thường biên dịch và chạy:

~~~java
static String title(Status status) {
    return switch (status) {
        case NEW -> "New";
        case ACTIVE -> "Active";
        case CLOSED -> "Closed";
        default -> "Other";
    };
}
~~~

Nếu `"Other"` là chính sách mong muốn cho các trạng thái mới, đây có thể là lựa chọn hợp lý. Nếu mọi trạng thái phải có bản dịch/tính toán riêng, `default` lại khiến việc bỏ sót `SUSPENDED` khó được phát hiện ngay ở biên dịch.

## 9. Ví dụ Java 17 hoàn chỉnh: chuyển đổi trạng thái đơn hàng

Tạo tệp `OrderStatusDemo.java` trong một thư mục trống:

~~~java
import java.util.Objects;

public final class OrderStatusDemo {
    private OrderStatusDemo() {
    }

    enum Status {
        CREATED, PAID, SHIPPED, DELIVERED, CANCELLED
    }

    static String label(Status status) {
        Objects.requireNonNull(status, "status");

        return switch (status) {
            case CREATED -> "Created";
            case PAID -> "Paid";
            case SHIPPED -> "Shipped";
            case DELIVERED -> "Delivered";
            case CANCELLED -> "Cancelled";
        };
    }

    static boolean canCancel(Status status) {
        Objects.requireNonNull(status, "status");

        return switch (status) {
            case CREATED, PAID -> true;
            case SHIPPED, DELIVERED, CANCELLED -> false;
        };
    }

    static int priority(Status status) {
        Objects.requireNonNull(status, "status");

        return switch (status) {
            case CREATED -> 10;
            case PAID -> 20;
            case SHIPPED -> {
                int base = 30;
                int trackingBonus = 5;
                yield base + trackingBonus;
            }
            case DELIVERED, CANCELLED -> 0;
        };
    }

    static String labelOrMissing(Status status) {
        if (status == null) {
            return "Missing status";
        }
        return label(status);
    }

    public static void main(String[] args) {
        for (Status status : Status.values()) {
            System.out.printf(
                    "%s -> %s, canCancel=%s, priority=%d%n",
                    status,
                    label(status),
                    canCancel(status),
                    priority(status));
        }

        System.out.println("Null input -> " + labelOrMissing(null));
    }
}
~~~

Mã ví dụ có bốn điểm quan trọng:

1. `label` ánh xạ đầy đủ năm giá trị enum **không có `default`**.
2. `canCancel` gom nhiều hằng có cùng ý nghĩa nghiệp vụ vào một nhánh, nhưng vẫn nêu đủ từng hằng.
3. `priority` dùng một block với `yield` để tính giá trị từ nhiều câu lệnh.
4. `labelOrMissing` thể hiện chính sách xử lý tham chiếu `null` **trước** khi gọi một switch đã đầy đủ cho các hằng enum.

Để biên dịch và chạy bằng JDK 17 từ thư mục chứa file:

~~~bash
javac --release 17 -encoding UTF-8 OrderStatusDemo.java
java OrderStatusDemo
~~~

Đầu ra dự kiến:

~~~text
CREATED -> Created, canCancel=true, priority=10
PAID -> Paid, canCancel=true, priority=20
SHIPPED -> Shipped, canCancel=false, priority=35
DELIVERED -> Delivered, canCancel=false, priority=0
CANCELLED -> Cancelled, canCancel=false, priority=0
Null input -> Missing status
~~~

`Status.values()` cho phép duyệt tất cả hằng enum được khai báo ở phiên bản hiện tại. Khi bổ sung một hằng mới, bạn có thể sửa `Status` rồi biên dịch lại để quan sát thông báo do các switch expression đang thiếu nhánh tương ứng.

### Thực hành thay đổi enum

Thử thêm `RETURNED`:

~~~java
enum Status {
    CREATED, PAID, SHIPPED, DELIVERED, CANCELLED, RETURNED
}
~~~

Sau đó biên dịch lại `OrderStatusDemo.java`. Các phương thức `label`, `canCancel` và `priority` hiện đều phải được bổ sung `RETURNED` vào nhánh phù hợp để lại trở nên đầy đủ. Đây là cách biến lỗi biên dịch thành một lời nhắc cập nhật hành vi nghiệp vụ.

Nếu chỉ thêm `default -> "Other"` vào `label` để vượt lỗi mà chưa xác định ý nghĩa của `RETURNED`, chương trình có thể chạy nhưng không đáp ứng yêu cầu hiển thị trạng thái mới. Hãy lựa chọn nhánh theo ý nghĩa thực tế trước khi quyết định thêm `default`.

## 10. Các lỗi thường gặp khi dùng `switch` trên enum

### 10.1. Thiếu một hằng và không có `default`

~~~java
// Giả sử Status có CREATED, PAID, SHIPPED, DELIVERED, CANCELLED.
String text = switch (status) {
    case CREATED -> "Created";
    case PAID -> "Paid";
    case SHIPPED -> "Shipped";
    case DELIVERED -> "Delivered";
}; // Lỗi: thiếu CANCELLED
~~~

**Nguyên nhân:** switch expression không đầy đủ. **Cách sửa:** thêm `case CANCELLED -> ...` hoặc thêm `default` nếu chính sách muốn gom các giá trị còn lại.

### 10.2. Nghĩ `default` sẽ bắt `null`

~~~java
// status == null
String text = switch (status) {
    case PAID -> "Paid";
    default -> "Other";
};
~~~

**Kết quả:** `NullPointerException` trên Java 17. **Cách sửa:** chọn một chính sách rõ ràng cho `null` trước switch, ví dụ `Objects.requireNonNull(status)` hoặc `if (status == null) return ...;`.

### 10.3. Dùng tên hằng enum có qualifier trong nhãn `case`

Đối với switch selector có kiểu `Status`, cách viết thông thường trong Java 17 là:

~~~java
case PAID -> "Paid";
~~~

Không viết nhãn hằng enum bằng `case Status.PAID -> ...` trong `switch` thông thường của Java 17. Tên hằng trong các nhánh phải theo cú pháp nhãn enum thích hợp; compiler đã biết kiểu selector từ `status`.

### 10.4. Quên `yield` khi có block nhiều câu lệnh

~~~java
// Không hợp lệ: nhánh dạng block không tạo giá trị.
int value = switch (status) {
    case PAID -> {
        int base = 10;
        int bonus = 5;
        // Thiếu yield base + bonus;
    }
    default -> 0;
};
~~~

**Cách sửa:** viết `yield base + bonus;` trong nhánh block, hoặc `throw` nếu đó là đường đi báo lỗi. Một switch expression không được kết thúc mà bỏ ngỏ giá trị của nó.

### 10.5. Dùng `break` để trả giá trị

Với switch expression trong Java 17, **không dùng `break someValue;`** như cú pháp trả giá trị của các bản thiết kế thử nghiệm cũ. Hãy dùng:

~~~java
int value = switch (status) {
    case PAID -> 1;
    default -> {
        int fallback = 0;
        yield fallback;
    }
};
~~~

`yield` là cú pháp ổn định để đưa giá trị ra khỏi một nhánh block của switch expression.

### 10.6. Dùng `default` để bỏ qua mọi trạng thái lạ

~~~java
return switch (status) {
    case CREATED -> "new";
    default -> "done";
};
~~~

Nếu `"done"` không đúng với `PAID`, `SHIPPED`, `CANCELLED` hoặc các trạng thái sẽ thêm sau này, `default` đang che giấu sai sót nghiệp vụ. Kiểm tra xem liệu **mọi giá trị còn lại** có thật sự cùng hành vi không trước khi chọn cách viết này.

### 10.7. Dựa vào thứ tự hằng thay vì tên và ý nghĩa

Mỗi `enum` có `ordinal()`, nhưng không nên dựa vào thứ tự `ordinal` để thực hiện ánh xạ nghiệp vụ lâu dài: khi chèn hoặc sắp xếp lại hằng, thứ tự có thể đổi. `switch` theo **tên hằng** rõ nghĩa và bền vững hơn trong các phép phân loại như `label` hoặc `canCancel`.

## 11. Lập ma trận kiểm thử cho tính đầy đủ

Compiler kiểm tra rằng switch expression trên enum có nhánh xử lý đủ kiểu tại thời điểm biên dịch, nhưng **không kiểm tra nội dung kết quả nghiệp vụ** của từng nhánh. Một hàm có thể xử lý đủ năm hằng mà vẫn trả sai giá trị cho `SHIPPED`.

Với ví dụ ở phần 9, ta có thể xây dựng bảng mong đợi:

| `Status` | `label` | `canCancel` | `priority` |
|---|---|---|---:|
| `CREATED` | `Created` | `true` | 10 |
| `PAID` | `Paid` | `true` | 20 |
| `SHIPPED` | `Shipped` | `false` | 35 |
| `DELIVERED` | `Delivered` | `false` | 0 |
| `CANCELLED` | `Cancelled` | `false` | 0 |

Bạn có thể dùng JUnit hoặc một framework kiểm thử của dự án để đối chiếu từng hàng. Đặc biệt, hãy đưa ca `null` vào nhóm kiểm thử riêng: chính sách `label(null)` (ném ngoại lệ) và `labelOrMissing(null)` (trả `Missing status`) là hai hợp đồng khác nhau.

Một bài kiểm thử Java đơn giản, không cần thư viện bên ngoài, có thể là:

~~~java
static void checkLabels() {
    for (Status status : Status.values()) {
        String actual = label(status);
        if (actual == null || actual.isBlank()) {
            throw new AssertionError("Missing label for " + status);
        }
    }
}
~~~

Vòng lặp này giúp phát hiện kết quả `null` hoặc trống cho một hằng, nhưng **không tự chứng minh** chuỗi `"Shipped"` đúng về nghiệp vụ. Để kiểm tra nội dung chính xác, hãy so sánh với giá trị mong đợi tương ứng cho từng hằng.

Nếu enum có thêm hằng mới và toàn bộ switch expression liệt kê hằng cũ mà không có `default`, lỗi biên dịch có thể xuất hiện **trước khi kiểm thử chạy**. Nếu có `default`, kiểm thử hành vi càng quan trọng để phát hiện ánh xạ không mong muốn.

## 12. Bài tập thực hành

### Bài tập 1 — Hoàn thiện switch expression

Cho:

~~~java
enum Priority {
    LOW, MEDIUM, HIGH, CRITICAL
}
~~~

Hoàn thiện phương thức sau sao cho biên dịch trên Java 17 **mà không cần `default`**:

~~~java
static int score(Priority priority) {
    return switch (priority) {
        case LOW -> 1;
        case MEDIUM -> 2;
        case HIGH -> 3;
        // Còn thiếu gì?
    };
}
~~~

Hãy giải thích vì sao trình biên dịch không chấp nhận phiên bản thiếu nhánh.

### Bài tập 2 — Dự đoán ảnh hưởng khi thêm hằng

Giả sử `Priority` được bổ sung `BLOCKER`. So sánh hai hàm:

~~~java
static String categoryA(Priority priority) {
    return switch (priority) {
        case LOW -> "slow";
        case MEDIUM -> "normal";
        case HIGH -> "fast";
        case CRITICAL -> "urgent";
    };
}

static String categoryB(Priority priority) {
    return switch (priority) {
        case LOW -> "slow";
        default -> "other";
    };
}
~~~

Khi biên dịch lại với enum có `BLOCKER`, hàm nào bị lỗi biên dịch? Hàm nào vẫn chạy, nhưng cần rà soát quy tắc gán nhóm?

### Bài tập 3 — Xử lý `null` theo hai chính sách

Viết hai phiên bản `describe(Priority priority)`:

1. Phiên bản từ chối `null` bằng `Objects.requireNonNull`.
2. Phiên bản trả về `"Missing priority"` khi `priority == null`.

Cả hai vẫn phải xử lý đầy đủ `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` bằng switch expression. Thử gọi mỗi phiên bản với `null` và với một hằng hợp lệ.

### Bài tập 4 — Dùng `yield` cho nhánh tính toán

Viết hàm `int estimateMinutes(Priority priority)` trả về `240` cho `LOW`, `120` cho `MEDIUM`, `60` cho `HIGH` và `15` cho `CRITICAL`. Riêng nhánh `HIGH` hãy dùng một block tính `baseMinutes - savedMinutes` rồi trả kết quả qua `yield`.

### Bài tập 5 — Cân nhắc `default` theo nghiệp vụ

Một ứng dụng có enum:

~~~java
enum PaymentState {
    CREATED, AUTHORIZED, CAPTURED, REFUNDED, FAILED
}
~~~

Yêu cầu là hiển thị **thông báo riêng cho từng trạng thái**. Hãy quyết định dùng hoặc bỏ `default`, rồi giải thích điều gì xảy ra khi thêm `PARTIALLY_REFUNDED` ở lần phát triển sau.

### Gợi ý đáp án

1. Thêm `case CRITICAL -> 4;`; khi thiếu hằng, switch expression chưa đầy đủ.
2. `categoryA` bị lỗi biên dịch khi xây dựng lại vì thiếu `BLOCKER`. `categoryB` vẫn có `default`, nên cần rà soát xem `"other"` có hợp lý.
3. `requireNonNull` ném `NullPointerException`; kiểm tra `null` trước switch có thể trả chuỗi thông báo. `default` trong switch không thay thế được hai cơ chế đó.
4. Dùng `case HIGH -> { int baseMinutes = 90; int savedMinutes = 30; yield baseMinutes - savedMinutes; }`.
5. Nên liệt kê tất cả các hằng và bỏ `default` nếu mọi trạng thái cần thông báo riêng. Khi thêm `PARTIALLY_REFUNDED`, biên dịch lại sẽ nhắc cập nhật nhánh.

## 13. Những nguyên tắc cần ghi nhớ

1. **`switch expression` luôn cần tính đầy đủ.** Mọi giá trị selector thuộc miền mà Java xét phải dẫn tới một nhánh tạo giá trị hoặc ném ngoại lệ.
2. Với **`enum`**, liệt kê đầy đủ các hằng cho phép **bỏ `default`**. Đây thường là cách tốt khi tất cả trạng thái phải được xử lý một cách có chủ đích.
3. **`default`** là công cụ xử lý các giá trị còn lại, không phải yêu cầu bắt buộc cho mọi switch trên enum. Sử dụng nó khi đó thật sự là chính sách nghiệp vụ.
4. **Thêm hằng enum rồi biên dịch lại** sẽ làm những switch expression liệt kê đủ hằng cũ nhưng không có `default` báo lỗi, buộc người viết xem xét nhánh mới.
5. **`default` không bắt `null`** trong switch thông thường của Java 17. Hãy chọn chính sách `null` trước khi vào switch.
6. Dùng **`->`** cho nhánh ngắn, và **`yield`** khi nhánh cần một block để tính giá trị. Tránh dựa vào các cú pháp preview hoặc hành vi cũ không còn được dùng.
7. Tính đầy đủ được kiểm tra bởi trình biên dịch **không thay thế kiểm thử kết quả**. Mỗi nhánh có thể tồn tại về cú pháp nhưng vẫn sai nghiệp vụ.

Từ những nguyên tắc đó, bạn có thể viết `switch expression` trên `enum` vừa ngắn gọn, vừa dễ theo dõi khi mô hình trạng thái thay đổi. Java 17 bảo vệ bạn trước việc bỏ sót hằng ngay lúc biên dịch, còn cách tổ chức `case` và sử dụng `default` quyết định chất lượng thiết kế lâu dài.

### Tài liệu tham khảo

- [Oracle Java 17 — Switch Expressions](https://docs.oracle.com/en/java/javase/17/language/switch-expressions.html).
- [Java SE 17 Language Specification — Section 14.11: The switch Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.11).
- [Java SE 17 Language Specification — Section 15.28: Switch Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28).
