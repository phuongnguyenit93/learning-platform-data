# Chọn biểu thức `switch` theo tính chất của phép phân loại

## Mục tiêu

Khi cần “xếp một giá trị vào nhóm nào đó”, không phải bài toán nào cũng nên viết `switch`. Bài này giúp bạn chọn **`switch expression`** khi dữ liệu được chia thành các trường hợp rời rạc, xác định rõ, đồng thời biết lúc nào nên dùng `if/else`, bảng tra cứu hoặc cơ chế phân phối khác.

Sau khi học, bạn có thể:

- Nhìn vào **đầu vào, quy tắc phân loại và đầu ra** để quyết định có nên dùng `switch expression`.
- Áp dụng `switch` cho `enum`, mã `String`, mã số nguyên và nhiều nhãn cùng kết quả.
- Phân biệt phân loại bằng **giá trị bằng nhau** với phân loại theo **khoảng giá trị**, **nhiều điều kiện phụ thuộc** hoặc **kiểu đối tượng**.
- Giữ biểu thức `switch` **đầy đủ các trường hợp (exhaustive)**, xử lý rõ giá trị không hợp lệ và `null`.
- Viết và chạy ví dụ Java 17 sử dụng cú pháp `switch expression` đã **chính thức từ Java 14**, không dùng cú pháp preview cũ.

## 1. “Tính chất của phép phân loại” là gì?

Một phép phân loại thường có ba thành phần:

1. **Đối tượng/khóa cần xét (selector):** ví dụ trạng thái đơn hàng `OrderState`, mã vùng `String`, mã phản hồi `int` hoặc điểm số.
2. **Quy tắc tạo nhóm:** so khớp với **từng giá trị cụ thể** như `NEW`, `SHIPPED`; xét **khoảng** như điểm từ 80 trở lên; hoặc xét **nhiều thuộc tính** đồng thời.
3. **Kết quả:** tên nhóm, mức phí, nhãn hiển thị, đối tượng chiến lược… hay một hành động cần thực thi.

`switch expression` phù hợp nhất khi:

- Có **một selector** mà ta so khớp được bằng các nhãn `case` rõ ràng.
- Mỗi trường hợp xác định một **giá trị kết quả**, chẳng hạn `String` hoặc `int`.
- Các nhánh có ý nghĩa **loại trừ nhau**, và mọi giá trị đầu vào hợp lệ đều có nhánh xử lý.
- Mục tiêu là **tính/chọn ra kết quả**, không chủ yếu thực hiện các hành động tạo tác dụng phụ.

Ví dụ: “Trạng thái `PACKED` hoặc `SENT` đều hiển thị nhãn `Đang giao`” là phép phân loại theo **giá trị rời rạc**, rất phù hợp với `switch expression`.

Ngược lại: “Đơn hàng có giá trị từ 500.000 trở lên *và* khách hàng là thành viên” là phép phân loại theo **khoảng + điều kiện phối hợp**. `if/else` thường biểu đạt quy tắc trực tiếp, dễ bảo trì hơn.

## 2. Chọn cấu trúc theo bản chất dữ liệu

| Bản chất bài toán | Ví dụ | Cách thường phù hợp | Lý do |
|---|---|---|---|
| **Tập giá trị đóng, xác định trước** | `enum` trạng thái đơn hàng → nhãn | **`switch expression` trên `enum`** | Các trường hợp hữu hạn, trình biên dịch kiểm tra độ bao phủ. |
| **Các mã hằng rời rạc** | `"HN"`, `"HCM"` → mức phí; mã `200` → nhãn | **`switch expression` trên `String`/`int`** | So khớp theo mã cụ thể, trả về một giá trị thống nhất. |
| **Nhiều mã vào cùng một nhóm** | `PENDING` và `REVIEWING` → `"Đang xử lý"` | **Một `case` chứa nhiều nhãn** | Cùng quy tắc nên cùng nhánh, tránh lặp biểu thức kết quả. |
| **Phân đoạn theo khoảng/thứ tự** | Điểm `>= 80`, `>= 65`, còn lại | **`if/else if`** | Trọng tâm là so sánh bất đẳng thức, không phải bằng một số hằng. |
| **Phân loại dựa trên nhiều yếu tố** | Điểm + trạng thái xác minh + loại tài khoản | **`if/else`, phương thức quy tắc hoặc chiến lược riêng** | Điều kiện phụ thuộc nhau; ép vào `switch` dễ tạo mã lồng nhau khó đọc. |
| **Bảng đối chiếu thay đổi theo dữ liệu/cấu hình** | Mã sản phẩm → nhãn cập nhật từ dữ liệu | **`Map` hoặc nguồn cấu hình** | Không cần sửa mã nguồn mỗi khi bảng thay đổi. |
| **Phân loại theo lớp/kiểu đối tượng** | `String`, `Integer`, kiểu domain khác nhau | **Pattern matching cho `switch` (Java 21+)** hoặc `instanceof` nếu cần hỗ trợ Java 17 | Đây là so khớp **kiểu/pattern**, khác với `case` hằng số của Java 14. |
| **Mỗi nhánh chủ yếu thực thi hành động** | Gửi email, ghi log, gọi dịch vụ | **`switch statement` hoặc điều phối hành vi** | Không cần tạo một giá trị chỉ để tận dụng `switch expression`. |

Bảng này là **hướng dẫn chọn cách diễn đạt**, không phải quy tắc “cứ có ba nhánh trở lên là bắt buộc dùng `switch`”. Ưu tiên cấu trúc diễn tả đúng quy tắc nghiệp vụ và rõ ràng khi thêm trường hợp mới.

## 3. Các dạng phân loại phù hợp với `switch expression`

### 3.1. Phân loại một `enum` có tập giá trị đóng

Giả sử hệ thống có sáu trạng thái giao hàng và cần ánh xạ sang bốn nhóm hiển thị:

~~~java
enum OrderState {
    CREATED, ACCEPTED, PACKED, SENT, DELIVERED, CANCELED
}

// Đoạn minh họa: đặt bên trong lớp có thể sử dụng OrderState.
static String stateGroup(OrderState state) {
    return switch (state) {
        case CREATED, ACCEPTED -> "Chuẩn bị";
        case PACKED, SENT -> "Đang giao";
        case DELIVERED -> "Hoàn tất";
        case CANCELED -> "Đã hủy";
    };
}
~~~

Vì tất cả hằng của `OrderState` đã được bao phủ, `switch expression` này **không cần `default`**. Đây là lợi thế khi mô hình `enum` là tập giá trị có chủ đích: nếu thêm hằng mới vào `enum` rồi biên dịch lại, trình biên dịch yêu cầu xử lý tính đầy đủ của biểu thức.

**Khi nào nên dùng `default`?** Với kiểu `enum` đóng mà **mỗi giá trị đều có ý nghĩa riêng**, thường nên liệt kê đầy đủ và bỏ `default` để bổ sung trạng thái mới không bị “nuốt” vào một nhánh chung. Nếu quy tắc nghiệp vụ thực sự có nhóm `OTHER` hợp lệ thì có thể biểu diễn nó bằng một hằng `enum` riêng hoặc một `default` được chủ động thiết kế.

**Điều kiện đầu vào:** `state == null` không phải một hằng `enum` hợp lệ; trong Java 17, `switch(state)` với `null` ném `NullPointerException`. Nếu `null` có thể xuất hiện, hãy xử lý trước khi `switch` theo chính sách nghiệp vụ.

### 3.2. Phân loại mã `String` hoặc mã số nguyên rời rạc

Khi các giá trị là mã có tập cố định, `switch expression` mô tả ánh xạ rõ ràng:

~~~java
// Đoạn minh họa: zone đã được kiểm tra khác null.
int fee = switch (zone) {
    case "HN", "HCM" -> 15_000;
    case "DN" -> 20_000;
    default -> throw new IllegalArgumentException("Vùng không hỗ trợ: " + zone);
};
~~~

Các con số là **chính sách giả định để minh họa**, không phải bảng giá thực tế.

Hai quyết định thiết kế quan trọng:

- **Chuẩn hóa khóa đầu vào** một lần (chẳng hạn `trim()`, `toUpperCase(Locale.ROOT)`) nếu mã nghiệp vụ không phân biệt chữ hoa/chữ thường. Đừng tự chuẩn hóa khi chữ hoa và chữ thường mang ý nghĩa khác nhau.
- **Xác định vai trò của `default`**: với một mã lạ, bạn muốn trả về nhóm “Khác” hợp lệ hay báo dữ liệu không hợp lệ? Cả hai đều có thể đúng, nhưng phải thể hiện đúng hợp đồng phương thức.

Trong Java 17, `String` có thể làm selector cho `switch`; với mã số nguyên, các nhãn như `case 200, 201 -> ...` cũng rõ ràng. Đừng nhầm `default` là nhánh bắt `null`: `switch` với selector tham chiếu `null` vẫn có thể ném `NullPointerException` trước khi chọn `default`.

### 3.3. Nhóm nhiều nhãn cùng một kết quả

Nếu nhiều giá trị có cùng ý nghĩa, gom chúng trong một nhánh thay vì chép lại giá trị trả về:

~~~java
String label = switch (statusCode) {
    case 200, 201, 204 -> "Thành công";
    case 400, 422 -> "Dữ liệu không hợp lệ";
    case 401, 403 -> "Không được phép";
    default -> "Khác";
};
~~~

Đây là phân loại theo các **mã chính xác**, không phải “mọi mã từ 200 đến 299 đều thành công”. Các nhãn số trên chỉ là tập ví dụ; nếu quy tắc thật sự bao phủ **cả một khoảng**, xem phần 4.

### 3.4. Nhánh cần tính toán trước khi cho ra kết quả: dùng `yield`

`case ... ->` có thể trả một biểu thức ngay. Khi một nhánh cần nhiều câu lệnh, mở khối `{ ... }` và dùng `yield` để trả giá trị từ **toàn bộ `switch expression`**:

~~~java
String message = switch (code) {
    case 404 -> {
        String resourceName = "Order";
        yield resourceName + " không tồn tại";
    }
    case 200 -> "Thành công";
    default -> "Mã chưa xác định";
};
~~~

Không dùng `break value` của các bản preview cũ; cú pháp chuẩn là `yield value;`. `yield` khác với `return`: `yield` kết thúc nhánh của **switch expression**, còn `return` trả về khỏi phương thức. Một nhánh khối không thể kết thúc bình thường mà bỏ quên giá trị cần `yield`, trừ khi luồng đó kết thúc bằng `throw`.

## 4. Khi nên chọn cách khác

### 4.1. Phân loại theo khoảng hoặc thứ tự: `if/else if`

Ví dụ phân nhóm điểm `0..100` thành ba mức. Cách diễn đạt trực tiếp là:

~~~java
// Đoạn minh họa: phương thức độc lập khi đặt trong một lớp.
static String scoreBand(int score) {
    if (score < 0 || score > 100) {
        throw new IllegalArgumentException("Điểm phải nằm trong 0..100");
    }
    if (score >= 80) {
        return "Giỏi";
    }
    if (score >= 65) {
        return "Khá";
    }
    return "Cần cải thiện";
}
~~~

Các điều kiện `>= 80` và `>= 65` có thứ tự ưu tiên, được kiểm tra từ trên xuống dưới. Trong **`switch` với các nhãn hằng kiểu Java 17**, không thể thay `case 80 -> ...` bằng một cách hiểu ngầm là “mọi điểm từ 80 trở lên”; `case 80` chỉ khớp **đúng 80**. Tránh liệt kê thủ công 21 giá trị chỉ để giả lập khoảng.

**Ngoại lệ hợp lý:** Nếu đã có một **mã nhóm rời rạc** được tính ở nơi khác vì lý do miền nghiệp vụ (ví dụ `ScoreBand` là `enum` chuẩn của hệ thống), có thể `switch` trên mã nhóm đó. Đừng tạo mã nhóm trung gian vô ích chỉ để đổi `if` thành `switch`.

### 4.2. Phân loại kết hợp nhiều thuộc tính: biểu diễn điều kiện trực tiếp

Ví dụ quy tắc phụ thuộc cả trạng thái đã xác minh và điểm rủi ro:

~~~java
static String riskTier(int riskScore, boolean verified) {
    if (!verified) {
        return "Cần xác minh";
    }
    if (riskScore < 0 || riskScore > 100) {
        throw new IllegalArgumentException("Điểm rủi ro không hợp lệ");
    }
    if (riskScore >= 80) {
        return "Rủi ro cao";
    }
    if (riskScore >= 50) {
        return "Rủi ro trung bình";
    }
    return "Rủi ro thấp";
}
~~~

Đây là đoạn mã minh họa cho chính sách giả định. Việc kiểm tra `verified` trước hay sau kiểm tra phạm vi điểm là **quyết định hợp đồng đầu vào**; ví dụ ưu tiên trạng thái “Cần xác minh”. Nếu yêu cầu “điểm sai luôn phải bị từ chối”, phải đưa bước kiểm tra phạm vi lên trước.

Khi điều kiện bắt đầu phức tạp, nên đặt tên quy tắc bằng phương thức riêng, dùng đối tượng chứa dữ liệu phân loại, hoặc dùng cơ chế chiến lược. Lồng nhiều `switch` chỉ để xử lý tổ hợp không tự động làm mã dễ hiểu hơn.

### 4.3. Ánh xạ thay đổi theo cấu hình: bảng tra cứu

Nếu bảng phân loại lớn và thường xuyên thay đổi theo cấu hình hoặc dữ liệu, `Map` phù hợp hơn chuỗi nhánh viết cứng:

~~~java
// Đoạn minh họa: giá trị mặc định "Chưa biết" là lựa chọn nghiệp vụ.
Map<String, String> labels = Map.of(
        "NEW", "Mới",
        "DONE", "Hoàn tất"
);
String label = labels.getOrDefault(status, "Chưa biết");
~~~

Đoạn này cần `import java.util.Map;` hoặc tên đầy đủ `java.util.Map`; nó giả sử `status` đã có sẵn. Với `enum` đóng và logic cố định, `switch expression` vẫn thường cho độ bao phủ lúc biên dịch rõ hơn `Map`. Nếu các giá trị đến từ database và thay đổi theo phiên bản dữ liệu, bảng tra cứu không buộc mỗi lần thêm khóa phải sửa cú pháp `case`.

### 4.4. Phân loại theo kiểu đối tượng: cân nhắc Java 21+

Đây là **một loại phân loại khác**: hỏi “đối tượng thuộc kiểu nào?” thay vì “mã này bằng hằng nào?”. **Pattern matching for switch** đã trở thành tính năng chuẩn ở **Java 21** theo [JEP 441](https://openjdk.org/jeps/441). Ví dụ Java 21+:

~~~java
// Java 21+, minh họa; không ghép nguyên văn vào chương trình Java 17 ở phần 5.
static String describe(Object value) {
    return switch (value) {
        case null -> "Không có dữ liệu";
        case String s -> "Chuỗi dài " + s.length();
        case Integer n -> n >= 0 ? "Số nguyên không âm" : "Số nguyên âm";
        default -> "Kiểu khác";
    };
}
~~~

Ở Java 17, đoạn trên **chưa phải cú pháp switch chuẩn**; dùng `if / instanceof` pattern matching (đã chuẩn từ Java 16) nếu cần hỗ trợ Java 17. Ở Java 21+, pattern `case null` cho phép xử lý `null` rõ ràng; không suy ngược khả năng đó về cú pháp `switch` Java 14.

### 4.5. Chỉ làm hành động: `switch statement` có thể phù hợp hơn

Nếu mỗi nhánh chủ yếu ghi log, gửi thông báo hoặc gọi dịch vụ mà không cần một kết quả, một `switch statement` diễn đạt mục tiêu trực tiếp:

~~~java
// Đoạn minh họa: action là một String đã được khai báo.
switch (action) {
    case "SAVE" -> System.out.println("Lưu");
    case "DELETE" -> System.out.println("Xóa");
    default -> System.out.println("Không hỗ trợ");
}
~~~

Đừng ép mỗi nhánh phải tạo một chuỗi giả rồi bỏ đi chỉ để dùng `switch expression`. Cả `switch statement` và `switch expression` đều có thể dùng nhãn mũi tên `->`, nhưng chỉ **expression** tạo ra giá trị để gán, trả về hoặc truyền vào biểu thức khác.

## 5. Ví dụ đầy đủ: chọn đúng công cụ cho ba kiểu phân loại

Tạo tệp **`SwitchClassificationGuide.java`**:

~~~java
import java.util.Locale;

public final class SwitchClassificationGuide {

    enum OrderState {
        CREATED, ACCEPTED, PACKED, SENT, DELIVERED, CANCELED
    }

    // Tập enum đóng: bao phủ hết các hằng, không cần default.
    static String stateGroup(OrderState state) {
        if (state == null) {
            throw new IllegalArgumentException("Trạng thái không được null");
        }
        return switch (state) {
            case CREATED, ACCEPTED -> "Chuẩn bị";
            case PACKED, SENT -> "Đang giao";
            case DELIVERED -> "Hoàn tất";
            case CANCELED -> "Đã hủy";
        };
    }

    // Mã String rời rạc: xác thực + chuẩn hóa một lần + giá trị trả về.
    static int deliveryFee(String zone) {
        if (zone == null) {
            throw new IllegalArgumentException("Vùng không được null");
        }
        String normalized = zone.trim().toUpperCase(Locale.ROOT);
        return switch (normalized) {
            case "HN", "HCM" -> 15_000;
            case "DN" -> 20_000;
            default -> throw new IllegalArgumentException(
                    "Vùng không hỗ trợ: " + normalized);
        };
    }

    // Khoảng liên tục: if/else thể hiện ranh giới đúng ý nghĩa.
    static String scoreBand(int score) {
        if (score < 0 || score > 100) {
            throw new IllegalArgumentException("Điểm phải nằm trong 0..100");
        }
        if (score >= 80) {
            return "Giỏi";
        }
        if (score >= 65) {
            return "Khá";
        }
        return "Cần cải thiện";
    }

    // Mã số nguyên: một nhánh có khối dùng yield.
    static String responseLabel(int code) {
        return switch (code) {
            case 200, 201 -> "Thành công";
            case 400, 422 -> "Dữ liệu không hợp lệ";
            case 404 -> {
                String explanation = "Không tìm thấy";
                yield explanation;
            }
            default -> "Khác";
        };
    }

    public static void main(String[] args) {
        System.out.println(stateGroup(OrderState.SENT));
        System.out.println(deliveryFee("  hcm  "));
        System.out.println(scoreBand(72));
        System.out.println(responseLabel(404));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 SwitchClassificationGuide.java
java SwitchClassificationGuide
~~~

Đầu ra chính xác:

~~~text
Đang giao
15000
Khá
Không tìm thấy
~~~

**Giải thích kết quả:**

1. `OrderState.SENT` nằm trong nhóm `PACKED, SENT`, nên nhận nhãn `Đang giao`; phương thức `stateGroup` dùng `switch expression` trên `enum`.
2. Chuỗi `"  hcm  "` được `trim()` và `toUpperCase(Locale.ROOT)` thành `"HCM"`, khớp nhãn và trả phí `15000`.
3. Điểm `72` nằm trong khoảng `65..79`, nên `if/else` trả `Khá`.
4. Mã `404` vào khối `case` và `yield` chuỗi `Không tìm thấy`.

Toàn bộ cú pháp `switch expression`, nhãn mũi tên, nhánh nhiều nhãn và `yield` trong chương trình đều đã là **tính năng chuẩn từ Java 14**; chạy với `--release 17` không cần `--enable-preview`.

## 6. Quy tắc kỹ thuật ảnh hưởng đến lựa chọn

### 6.1. `switch expression` bắt buộc bao phủ mọi trường hợp

Nếu `switch` tạo **giá trị**, trình biên dịch phải xác định mọi đường đi hợp lệ đều có kết quả hoặc ném ngoại lệ. Với `String`/`int` trên Java 17, thông thường cần `default`. Với `enum`, có thể liệt kê toàn bộ hằng và bỏ `default`.

Hãy đặt câu hỏi: **“Nếu mai có thêm trạng thái/mã mới, hệ thống nên báo thiếu nhánh hay tự đưa vào nhóm mặc định?”** Câu trả lời giúp quyết định thiết kế `default`.

### 6.2. Các nhánh phải trả giá trị phù hợp với kiểu cần dùng

Ví dụ `int fee = switch (...) { ... };` yêu cầu mọi giá trị kết quả tương thích với `int` hoặc một nhánh ném ngoại lệ. Tránh trả lung tung `String`, `int` và đối tượng khác nhau chỉ vì có thể ép kiểu chung: biểu thức phân loại nên có **hợp đồng đầu ra rõ ràng**.

Trong một nhánh khối, dùng `yield` để cấp kết quả. Không dùng `break` để xuất giá trị khỏi `switch expression`; `break` thuộc ngữ nghĩa điều khiển khác.

### 6.3. Cần chính sách rõ ràng cho `null` và mã không hợp lệ

- Trong chương trình Java 17 này, ta **kiểm tra `null` trước `switch`**. `default` không tự bắt `null`.
- Giá trị không có trong bảng có thể là **nhóm `OTHER` hợp lệ** hoặc **lỗi đầu vào**. Hãy lựa chọn theo miền nghiệp vụ; đừng dùng một `default` trả `0`/`""` làm che mất dữ liệu lỗi.
- Java 21 có `case null` trong pattern `switch` chuẩn, nhưng chỉ dùng cú pháp đó khi mức Java đích thực sự hỗ trợ.

### 6.4. Nhãn `case` mô tả tập giá trị, không phải mọi phép kiểm tra

`case 1, 2, 3 -> ...` diễn tả **ba giá trị cụ thể**. Nó không biểu diễn điều kiện `1 <= x && x <= 3` như một công thức miền giá trị có thể thay đổi. Nếu phần lớn điều kiện là bất đẳng thức, biểu thức logic hoặc nhiều trường dữ liệu, hãy viết trực tiếp các điều kiện.

### 6.5. Không nhầm một `switch statement` với một `switch expression`

So sánh:

~~~java
// Expression: tạo một giá trị để dùng ngay.
String result = switch (statusCode) {
    case 200 -> "OK";
    default -> "Khác";
};

// Statement: thực thi hành động, không tạo giá trị từ switch.
switch (statusCode) {
    case 200 -> System.out.println("OK");
    default -> System.out.println("Khác");
}
~~~

Hai đoạn đều là **mã minh họa trong một phương thức**, giả định `statusCode` có kiểu `int`. Việc dùng mũi tên `->` không tự biến một `switch statement` thành `switch expression`; **ngữ cảnh sử dụng** quyết định cấu trúc.

## 7. Các lỗi thiết kế dễ gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Dùng `switch` cho ngưỡng điểm, tuổi, giá tiền | Liệt kê nhiều hằng, bỏ sót khoảng và khó sửa chính sách | Dùng `if/else if` với các ranh giới rõ ràng |
| Gom nhiều thuộc tính vào chuỗi khóa giả như `"VIP_HIGH_VERIFIED"` | Phụ thuộc định dạng mã ghép, số trường hợp tăng nhanh | Viết điều kiện trực tiếp hoặc đặt tên quy tắc riêng |
| Thêm `default -> "Khác"` vô điều kiện cho mọi `enum` | Có thể che đi trạng thái mới cần xử lý nghiệp vụ | Bao phủ tất cả hằng `enum` và cân nhắc bỏ `default` |
| Không kiểm tra `null` trước khi `switch` trên `String` trong Java 17 | `NullPointerException` trước khi vào `default` | Xác thực đầu vào; nếu dùng Java 21+, cân nhắc `case null` |
| Dùng `yield` và `return` như thể tương đương | Trả về sai phạm vi hoặc lỗi biên dịch | `yield` trả giá trị từ `switch expression`; `return` trả khỏi phương thức |
| Dùng `switch expression` chỉ để gọi dịch vụ có tác dụng phụ | Cần tạo giá trị thừa, khó đọc ý định | Dùng `switch statement` hoặc phương thức điều phối |
| Viết một `case` cho mọi mã có thể thay đổi theo dữ liệu | Bảng mã phình to, phải biên dịch lại khi dữ liệu đổi | Dùng `Map`/cấu hình nếu mô hình thực sự dựa trên dữ liệu |
| Dùng cú pháp pattern `case String s` của Java 21 trong nguồn Java 17 | Không biên dịch theo mức Java 17 chuẩn | Với Java 17, dùng `if / instanceof` hoặc case hằng hợp lệ |

## 8. Quy trình chọn nhanh

Trước khi viết biểu thức, trả lời lần lượt:

1. **Bài toán cần tạo một kết quả hay thực hiện hành động?** Nếu chủ yếu hành động, cân nhắc `switch statement`/dispatch; nếu cần giá trị, tiếp tục.
2. **Phân loại theo đúng một khóa rời rạc có các nhãn hằng rõ ràng không?** Nếu có, `switch expression` là ứng viên tốt.
3. **Các nhánh có thể liệt kê đầy đủ không?** Với `enum` đóng, liệt kê mọi hằng; với tập mã mở, quyết định `default` trả nhóm hợp lệ hay ném lỗi.
4. **Quy tắc thực tế có dựa trên khoảng hoặc nhiều thuộc tính không?** Nếu có, cân nhắc `if/else` hoặc các quy tắc được đóng gói.
5. **Bảng mã có thay đổi theo dữ liệu bên ngoài không?** Nếu có, cân nhắc `Map`/config.
6. **Có `null`, mã chưa biết hoặc chuẩn hóa khóa không?** Xác định cách xử lý trước khi hoàn tất phương thức.
7. **Mức Java tối thiểu của dự án là bao nhiêu?** Java 14+ đã có `switch expression` chuẩn; pattern `switch` dựa trên kiểu đã chuẩn từ Java 21.

## 9. Tự luyện tập và đáp án

**Bài 1.** Biến `direction` là `enum { NORTH, SOUTH, EAST, WEST }`, mỗi hướng tương ứng một ký hiệu mũi tên. Nên chọn cấu trúc nào?

**Đáp án:** `switch expression` trên `enum`; bốn trường hợp rời rạc, mỗi trường hợp cho ra một `String`. Có thể bao phủ đủ bốn hằng mà không cần `default`.

**Bài 2.** Phân nhóm nhiệt độ: dưới 18 °C là lạnh, 18–29 °C là vừa, 30 °C trở lên là nóng. Có nên liệt kê từng số nguyên trong `case`?

**Đáp án:** Không. Các **khoảng** mới là quy tắc chính. Dùng `if/else if`; cũng cần xác định dữ liệu có phải số nguyên không và cách xử lý biên với số thực.

**Bài 3.** Mã chức năng `"READ"`, `"WRITE"`, `"DELETE"` được ánh xạ thành nhãn hiển thị; mã lạ phải báo lỗi. Chọn gì?

**Đáp án:** `switch expression` trên `String` với mỗi nhánh trả nhãn, `default -> throw new IllegalArgumentException(...)` và quy tắc kiểm tra `null` rõ ràng.

**Bài 4.** Bảng mã → nhãn có 500 dòng và được bộ phận nghiệp vụ cập nhật hằng tuần, không phải bản phát hành mã nguồn. Chọn gì?

**Đáp án:** Bảng tra cứu/cấu hình có thể cập nhật theo dữ liệu; `switch` với hàng trăm nhánh không phản ánh bản chất thay đổi của dữ liệu.

**Bài 5.** Một giá trị có thể là `String` hoặc `Integer`, và cần phân loại theo **kiểu**. Dự án yêu cầu chạy Java 17. Chọn gì?

**Đáp án:** `if / instanceof` pattern matching (cú pháp đã chuẩn ở Java 16) phù hợp Java 17. Chỉ chọn pattern matching cho `switch` nếu dự án cho phép Java 21 trở lên.

## Tài liệu tham khảo

- [OpenJDK — JEP 361: Switch Expressions](https://openjdk.org/jeps/361): mốc chuẩn hóa tại Java 14, nhãn mũi tên, `yield` và yêu cầu exhaustive.
- [Oracle Java 14 — Switch Expressions](https://docs.oracle.com/en/java/javase/14/language/switch-expressions.html): cú pháp Java 14, nhánh nhiều nhãn và tính đầy đủ.
- [Oracle Java 21 — Switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/switch-expressions-and-statements.html): phân biệt expression/statement và các quy tắc `case`.
- [OpenJDK — JEP 441: Pattern Matching for switch](https://openjdk.org/jeps/441): mốc chính thức Java 21 dành cho phân loại theo kiểu/pattern.
- [Oracle Java 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): `case null`, kiểu đối tượng, điều kiện `when` và tính đầy đủ.

**Điểm cốt lõi:** Hãy dùng `switch expression` khi phép phân loại là **ánh xạ từ một khóa rời rạc sang một giá trị rõ ràng**. Nếu quy tắc chủ yếu là **khoảng, điều kiện phối hợp hoặc dữ liệu cấu hình động**, hãy chọn cấu trúc thể hiện đúng quy tắc đó.