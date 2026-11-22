# Tránh điều kiện lồng quá sâu khi kết hợp patterns (Java 21+)

## 1. Vấn đề: điều kiện càng lồng sâu càng khó theo dõi

Trong chương trình Java, một phép xử lý thường phải kiểm tra liên tiếp: đối tượng có đúng kiểu không, dữ liệu con có tồn tại không, thuộc tính có hợp lệ không, và trạng thái nghiệp vụ có cho phép xử lý không. Nếu mỗi kiểm tra nằm trong một khối `if` mới, mã sẽ thành nhiều tầng:

~~~java
if (input instanceof Order order) {
    if (order.buyer() != null) {
        if (order.buyer().verified()) {
            // ... còn những điều kiện khác ...
        }
    }
}
~~~

Cách viết này không sai về ngữ nghĩa. Vấn đề là **luồng chính bị đẩy sang phải**, phải nhớ nhiều điều kiện đang bao quanh dòng xử lý, khó xác định đường đi thất bại và dễ bỏ sót `null` khi thay đổi cấu trúc dữ liệu.

**Pattern matching** giúp kiểm tra kiểu và lấy giá trị trong cùng biểu thức; **record pattern** còn phân rã các thành phần của `record`. Kết hợp đúng với **guard clause** (trả về sớm), `&&`, hàm trợ giúp và `switch` có thể giảm số khối lồng nhau mà vẫn giữ nguyên hành vi.

Đích đến không nhất thiết là **ít dòng nhất**: cách tổ chức tốt phải thể hiện rõ điều kiện nào bắt buộc, điều kiện nào là quy tắc nghiệp vụ, và hành vi nào xảy ra khi không khớp.

Bài sử dụng **Java 21+**, phiên bản mà record pattern và pattern matching trong `switch` đã chính thức được hỗ trợ.

## 2. Một bài toán xuyên suốt

Giả sử hệ thống chỉ duyệt đơn hàng khi:

1. Đầu vào thực sự là một `Order`.
2. `Order` có người mua `User`.
3. Người mua đã xác minh (`verified == true`).
4. Tên người mua khác `null` và không chứa toàn khoảng trắng.
5. Tổng tiền `total >= 100`.
6. Trạng thái đơn hàng là `"PAID"`.

Hai record đơn giản:

~~~java
record User(String name, boolean verified) {}
record Order(User buyer, int total, String status) {}
~~~

Đầu vào có kiểu tĩnh `Object` vì có thể đến từ nhiều nguồn. Nếu một điều kiện không đạt, quyết định duyệt phải là `false`. Khi cần trả về nhãn trạng thái, quy ước: `"APPROVED"` nếu đủ điều kiện, `"REJECTED"` nếu là `Order` nhưng không đủ điều kiện, `"INVALID"` nếu đầu vào là `null` hoặc không phải `Order`.

### Cách viết lồng nhiều tầng

~~~java
static boolean nested(Object input) {
    if (input instanceof Order order) {
        if (order.buyer() != null) {
            if (order.buyer().verified()) {
                if (order.buyer().name() != null) {
                    if (!order.buyer().name().isBlank()) {
                        if (order.total() >= 100) {
                            if ("PAID".equals(order.status())) {
                                return true;
                            }
                        }
                    }
                }
            }
        }
    }
    return false;
}
~~~

Đây là **một phương thức minh họa**; đặt nó trong lớp có hai khai báo `User` và `Order` phía trên. Nó xử lý đúng bài toán, nhưng sáu tầng điều kiện khiến người đọc phải đi sâu mới tới kết quả. Các lần gọi `order.buyer()` và `order.buyer().name()` cũng bị lặp.

Ta có thể cải thiện theo từng bước thay vì rút gọn tất cả bằng một biểu thức khó hiểu.

## 3. Cách 1: record pattern + guard clause

~~~java
static boolean flattened(Object input) {
    if (!(input instanceof Order(
            User(var name, var verified),
            var total, var status))) {
        return false;
    }

    return verified
            && name != null
            && !name.isBlank()
            && total >= 100
            && "PAID".equals(status);
}
~~~

### Vì sao không cần nhiều tầng `if`?

- `Order(...)` kiểm tra đối tượng đầu vào là `Order` và phân rã ba thành phần `buyer`, `total`, `status`.
- `User(var name, var verified)` là **record pattern lồng bên trong**: component `buyer` phải là một `User` khác `null` để mẫu khớp, rồi tạo các biến `name` và `verified`.
- Nếu record pattern không khớp, nhánh phủ định `if (!(...))` trả về `false` ngay. Mọi đường thực thi còn tiếp tục sau `if` đều đã khớp mẫu.
- Nhờ **flow scoping**, các biến mẫu `name`, `verified`, `total`, `status` vẫn hợp lệ ở câu lệnh `return` phía sau guard clause.
- Các quy tắc nghiệp vụ lúc này thành một biểu thức điều kiện phẳng, có thể đọc từ trên xuống.

Phải phân biệt **giá trị record lồng** và **giá trị component bên trong**: `buyer == null` khiến `User(...)` không khớp. Nhưng nếu `buyer` tồn tại và `name == null`, mẫu `var name` vẫn nhận giá trị `null`; ta cần kiểm tra `name != null` trước `name.isBlank()`.

Cách viết `"PAID".equals(status)` an toàn khi `status == null`. Cách viết `status.equals("PAID")` có thể ném `NullPointerException` nếu không kiểm tra `status` trước.

Guard clause đặc biệt hữu ích khi nhánh “không thể xử lý” ngắn và luồng còn lại mới là nội dung chính. Có thể thay `return` bằng `throw` khi đầu vào sai là lỗi cần báo, nhưng thay đổi đó sẽ **thay đổi hành vi**; không nên áp dụng chỉ vì muốn ít tầng `if`.

## 4. Cách 2: kết hợp pattern và `&&` ngay trong một biểu thức

Nếu cần một kết quả boolean gọn, có thể tận dụng đánh giá ngắn mạch:

~~~java
static boolean combined(Object input) {
    return input instanceof Order(
            User(var name, var verified),
            var total, var status)
            && verified
            && name != null
            && !name.isBlank()
            && total >= 100
            && "PAID".equals(status);
}
~~~

Java đánh giá `&&` từ **trái sang phải**. Khi mẫu ở đầu không khớp, phần còn lại không được đánh giá; các biến mẫu không bị sử dụng trong đường đi không hợp lệ. Khi mẫu khớp, `verified`, `name`, `total` và `status` nằm trong phạm vi hợp lệ ở các vế tiếp theo.

Thứ tự điều kiện quan trọng:

~~~java
name != null && !name.isBlank()  // An toàn
~~~

khác với:

~~~java
!name.isBlank() && name != null  // Có thể ném NullPointerException
~~~

Lưu ý thêm:

- Không thể đổi `&&` thành `||` một cách máy móc. Nếu vế trái `instanceof` sai, vế phải của `||` có thể chạy khi biến mẫu chưa có phạm vi hợp lệ.
- `&&` hợp với điều kiện ngắn, một đường xử lý. Nếu biểu thức dài đến mức khó xem từng quy tắc, dùng guard clause hoặc tách hàm.
- Đừng lẫn **kiểm tra hình dạng dữ liệu** với **quy tắc nghiệp vụ**: record pattern xác nhận đúng cấu trúc; `verified`, ngưỡng `total` và `status` là điều kiện nghiệp vụ được xét sau đó.

## 5. Cách 3: tách quy tắc nghiệp vụ thành hàm có tên rõ ràng

Đôi khi vấn đề chính không phải số tầng `if` mà là một biểu thức có quá nhiều điều kiện. Hãy tách phần kiểm tra người mua:

~~~java
static boolean validBuyer(User buyer) {
    return buyer != null
            && buyer.verified()
            && buyer.name() != null
            && !buyer.name().isBlank();
}

static boolean helper(Object input) {
    if (!(input instanceof Order order)) {
        return false;
    }

    return validBuyer(order.buyer())
            && order.total() >= 100
            && "PAID".equals(order.status());
}
~~~

Ở đây `instanceof Order order` là **type pattern**: kiểm tra kiểu và tạo biến `order`. Hàm `validBuyer` gom các điều kiện thuộc cùng trách nhiệm; `helper` thể hiện rõ điều kiện cấp đơn hàng.

Cách này phù hợp khi quy tắc “người mua hợp lệ” được sử dụng ở nhiều nơi hoặc cần kiểm thử độc lập. Tránh tạo một hàm riêng cho từng phép so sánh quá nhỏ nếu việc tách làm người đọc phải liên tục nhảy qua nhiều phương thức mới hiểu được luồng chính.

So sánh nhanh:

| Cách | Điểm mạnh | Dùng khi |
| --- | --- | --- |
| `if` lồng nhiều tầng | Mỗi mức có vị trí xử lý riêng | Các nhánh thật sự có thao tác khác nhau, không chỉ kiểm tra đúng/sai |
| Record pattern + guard clause | Loại đầu vào không hợp lệ sớm, phần chính ít thụt lề | Cần xử lý tiếp sau khi mẫu khớp |
| Record pattern + `&&` | Điều kiện boolean ngắn, đánh giá ngắn mạch | Chỉ cần kết quả đúng/sai với một số điều kiện dễ đọc |
| Hàm `validBuyer` + type pattern | Quy tắc nghiệp vụ có tên và tái sử dụng được | Quy tắc dài, lặp lại hoặc cần kiểm thử riêng |

Không có cách nào luôn tốt hơn: mục tiêu là làm rõ các điều kiện **theo mối quan hệ** của chúng, đồng thời giữ nguyên ngữ nghĩa.

## 6. Cách 4: dùng `switch` với `when` nếu có nhiều kết quả

Khi cần phân loại thành nhiều kết quả, chuỗi `if/else if` lồng nhau cũng dễ khó đọc. `switch` có pattern và `when` có thể diễn đạt từng trường hợp:

~~~java
static String classify(Object input) {
    return switch (input) {
        case Order(User(var name, var verified), var total, var status)
                when verified && name != null && !name.isBlank()
                        && total >= 100 && "PAID".equals(status)
                -> "APPROVED";

        case Order(var buyer, var total, var status) -> "REJECTED";
        case null -> "INVALID";
        default -> "INVALID";
    };
}
~~~

Ở nhánh đầu, record pattern phân rã `User` và `Order`; **guard `when`** chỉ được đánh giá nếu pattern đã khớp. Các biến mẫu có phạm vi ở điều kiện `when` và biểu thức kết quả của chính nhánh đó.

Nhánh `case Order(var buyer, var total, var status)` rộng hơn: mọi `Order` chưa được duyệt đều trả về `"REJECTED"`, kể cả đơn có `buyer == null`. Sự khác biệt này quan trọng vì nhánh duyệt đầu tiên chứa mẫu lồng `User(...)` và sẽ **không** khớp nếu người mua `null`.

`case null` xử lý chính đối tượng đầu vào `null`; `default` xử lý các đối tượng không phải `Order`. Đặt nhánh cụ thể có `when` **trước** nhánh `Order(...)` bao quát để tránh che khuất các nhánh cụ thể.

`switch` hữu ích khi cần **phân loại** thành nhiều kết quả. Nếu chỉ cần boolean, một `return` với `&&` thường đơn giản hơn. Nếu từng điều kiện cần trả lý do chi tiết, một chuỗi guard clause với thông báo rõ ràng có thể dễ bảo trì hơn `switch` gồm nhiều guard dài.

## 7. Chương trình Java 21 hoàn chỉnh: kiểm tra các cách viết tương đương

Lưu nguyên chương trình sau vào tệp **`PatternDepthDemo.java`**. Nó so sánh cả năm cách xử lý (điều kiện lồng, guard clause, `&&`, hàm phụ trợ và phân loại `switch`) trên mười một trường hợp, gồm các trường hợp không đủ điều kiện và giá trị `null`.

~~~java
public class PatternDepthDemo {
    record User(String name, boolean verified) {}
    record Order(User buyer, int total, String status) {}
    record Sample(String label, Object value, String expected) {}

    static boolean nested(Object input) {
        if (input instanceof Order order) {
            if (order.buyer() != null) {
                if (order.buyer().verified()) {
                    if (order.buyer().name() != null) {
                        if (!order.buyer().name().isBlank()) {
                            if (order.total() >= 100) {
                                if ("PAID".equals(order.status())) {
                                    return true;
                                }
                            }
                        }
                    }
                }
            }
        }
        return false;
    }

    static boolean flattened(Object input) {
        if (!(input instanceof Order(
                User(var name, var verified),
                var total, var status))) {
            return false;
        }
        return verified && name != null && !name.isBlank()
                && total >= 100 && "PAID".equals(status);
    }

    static boolean combined(Object input) {
        return input instanceof Order(
                User(var name, var verified),
                var total, var status)
                && verified && name != null && !name.isBlank()
                && total >= 100 && "PAID".equals(status);
    }

    static boolean validBuyer(User buyer) {
        return buyer != null && buyer.verified()
                && buyer.name() != null && !buyer.name().isBlank();
    }

    static boolean helper(Object input) {
        if (!(input instanceof Order order)) {
            return false;
        }
        return validBuyer(order.buyer()) && order.total() >= 100
                && "PAID".equals(order.status());
    }

    static String classify(Object input) {
        return switch (input) {
            case Order(User(var name, var verified), var total, var status)
                    when verified && name != null && !name.isBlank()
                            && total >= 100 && "PAID".equals(status)
                    -> "APPROVED";
            case Order(var buyer, var total, var status) -> "REJECTED";
            case null -> "INVALID";
            default -> "INVALID";
        };
    }

    public static void main(String[] args) {
        Sample[] samples = {
            new Sample("eligible",
                    new Order(new User("Lan", true), 150, "PAID"),
                    "APPROVED"),
            new Sample("boundary-100",
                    new Order(new User("Lan", true), 100, "PAID"),
                    "APPROVED"),
            new Sample("unverified",
                    new Order(new User("Lan", false), 150, "PAID"),
                    "REJECTED"),
            new Sample("low-total",
                    new Order(new User("Lan", true), 99, "PAID"),
                    "REJECTED"),
            new Sample("wrong-status",
                    new Order(new User("Lan", true), 150, "PENDING"),
                    "REJECTED"),
            new Sample("null-status",
                    new Order(new User("Lan", true), 150, null),
                    "REJECTED"),
            new Sample("null-buyer",
                    new Order(null, 150, "PAID"),
                    "REJECTED"),
            new Sample("null-name",
                    new Order(new User(null, true), 150, "PAID"),
                    "REJECTED"),
            new Sample("blank-name",
                    new Order(new User("  ", true), 150, "PAID"),
                    "REJECTED"),
            new Sample("null-input", null, "INVALID"),
            new Sample("other-type", "not-an-order", "INVALID")
        };

        int passed = 0;
        for (Sample s : samples) {
            boolean expectedEligible = s.expected().equals("APPROVED");
            boolean same = nested(s.value()) == expectedEligible
                    && flattened(s.value()) == expectedEligible
                    && combined(s.value()) == expectedEligible
                    && helper(s.value()) == expectedEligible
                    && classify(s.value()).equals(s.expected());
            if (!same) {
                throw new AssertionError("Mismatch at " + s.label());
            }
            passed++;
            System.out.println(s.label() + " -> " + classify(s.value()));
        }
        System.out.println("PASS " + passed + "/" + samples.length);
    }
}
~~~

Chạy với **JDK 21 trở lên**:

~~~bash
javac --release 21 PatternDepthDemo.java
java PatternDepthDemo
~~~

Kết quả mong đợi:

~~~text
eligible -> APPROVED
boundary-100 -> APPROVED
unverified -> REJECTED
low-total -> REJECTED
wrong-status -> REJECTED
null-status -> REJECTED
null-buyer -> REJECTED
null-name -> REJECTED
blank-name -> REJECTED
null-input -> INVALID
other-type -> INVALID
PASS 11/11
~~~

Phương thức `main` kiểm tra từng ca theo **kỳ vọng xác định trước**. Nó cũng xác nhận cả bốn cách viết boolean đồng ý với nhau và hàm `classify` trả đúng nhãn. Nếu bất kỳ cách viết nào khác kết quả kỳ vọng, chương trình ném `AssertionError` trước khi in `PASS 11/11`.

Một điểm cần lưu ý: phép kiểm tra tương đương phải bao gồm **các trường hợp thất bại**, không chỉ đầu vào hợp lệ. Chẳng hạn, chuyển từ `if (order.buyer() != null)` sang một record pattern lồng có thể an toàn vì `User(...)` không khớp `null`; nhưng nếu bỏ mất điều kiện `name != null` thì lời gọi `name.isBlank()` ở vế sau có thể gặp lỗi.

## 8. Vì sao thứ tự điều kiện, `null` và phạm vi biến lại quan trọng?

### 8.1. Toán tử ngắn mạch giữ cho bước sau an toàn

~~~java
name != null && !name.isBlank()
~~~

được phép dùng vì Java chỉ gọi `isBlank()` khi `name != null`. Với biểu thức dài, nên đặt các điều kiện **bắt buộc để truy cập an toàn** trước điều kiện sử dụng giá trị.

### 8.2. Biến mẫu có phạm vi theo luồng điều khiển

~~~java
if (!(input instanceof Order(User(var name, var verified),
                             var total, var status))) {
    return false;
}

// Hợp lệ: đường đi không khớp đã kết thúc.
System.out.println(name);
~~~

Đây là **đoạn minh họa** trong một phương thức có kiểu `User` và `Order` thích hợp; nó không phải chương trình độc lập. Nếu bỏ `return false` và vẫn dùng `name` sau `if`, Java không còn bảo đảm biến mẫu đã được tạo.

Vế phải của `&&` cũng dùng được biến mẫu vì chỉ chạy sau khi vế trái khớp. Ngược lại, biểu thức dạng sau **không hợp lệ**:

~~~java
// CỐ Ý SAI: ở vế phải của ||, pattern bên trái có thể chưa khớp.
if (input instanceof Order(User(var name, var verified),
                           var total, var status)
        || verified) {
    // ...
}
~~~

Ví dụ này chỉ minh họa lỗi phạm vi và không nằm trong tệp biên dịch được ở mục 7.

### 8.3. Record pattern lồng không tự loại bỏ mọi giá trị `null`

| Dữ liệu | Mẫu `Order(User(...), ...)` | Lý do |
| --- | --- | --- |
| `input == null` | Không khớp | `instanceof` với `null` là `false`. |
| `new Order(null, 150, "PAID")` | Không khớp | Component `buyer` không khớp mẫu record `User(...)`. |
| `new Order(new User(null, true), 150, "PAID")` | Có thể khớp mẫu, nhưng không được duyệt | `var name` có thể nhận `null`; điều kiện nghiệp vụ loại giá trị này. |
| `new Order(new User("Lan", true), 150, null)` | Có thể khớp mẫu, nhưng không được duyệt | `var status` nhận `null`, còn `"PAID".equals(status)` trả `false`. |
| Đối tượng khác `Order` | Không khớp | Kiểm tra kiểu ngoài cùng thất bại. |

Điểm mấu chốt: **pattern xác định cấu trúc dữ liệu**, còn các điều kiện sau pattern phải kiểm tra những quy tắc mà cấu trúc chưa bảo đảm, chẳng hạn tên không rỗng hay trạng thái thanh toán.

## 9. Những sai lầm khi rút gọn điều kiện

**Sai 1 — gom tất cả vào một dòng cực dài.** Ít tầng `if` không có nghĩa là dễ đọc. Hãy xuống dòng ở từng điều kiện, đặt tên quy tắc rõ ràng hoặc tách hàm khi cần.

**Sai 2 — thay đổi hành vi khi refactor.** Mã cũ có thể trả `false` nếu đầu vào không hợp lệ, nhưng mã mới lại ném ngoại lệ hoặc coi `null` là hợp lệ. Trước khi thay, ghi lại các ca biên và kiểm thử cùng đầu ra.

**Sai 3 — bỏ kiểm tra `null` sau khi dùng record pattern.** Record pattern lồng loại bỏ `null` ở vị trí cần khớp record; nó **không bảo đảm** mọi component kiểu tham chiếu bên trong đều khác `null`, đặc biệt với `var`.

**Sai 4 — nghĩ rằng `&&` và `||` có thể hoán đổi.** Cấu trúc đánh giá ngắn mạch và phạm vi biến mẫu khác nhau. Luôn xem chính xác đường đi nào sẽ đánh giá biểu thức phía sau.

**Sai 5 — dùng `switch` cho một điều kiện boolean đơn giản.** Nếu chỉ có một quy tắc đúng/sai, `instanceof` với `&&` hoặc guard clause dễ hiểu hơn. `switch` phát huy tác dụng khi thực sự có nhiều loại đối tượng hay nhiều kết quả cần phân biệt.

**Sai 6 — lạm dụng record pattern lồng quá sâu.** Dạng như `Envelope(Document(Owner(Address(...))))` tuy có thể diễn đạt cấu trúc, nhưng trở nên khó đọc nếu kèm nhiều guard. Có thể phân rã một hoặc hai tầng, đưa quy tắc vào hàm có tên và giữ cấu trúc rõ ràng.

**Sai 7 — đặt nhánh tổng quát lên trước nhánh cụ thể trong `switch`.** Với mẫu chung `case Order(...)`, các trường hợp `Order` phía sau có thể bị che khuất; ưu tiên nhánh cụ thể có guard trước nhánh dự phòng.

**Sai 8 — mất thông tin lý do từ chối.** Biểu thức boolean phẳng rất phù hợp để kiểm tra điều kiện đủ, nhưng nếu sản phẩm cần hiển thị “chưa xác minh” hay “chưa thanh toán”, nên dùng các bước trả về lý do cụ thể. Đừng hy sinh thông tin nghiệp vụ chỉ để tiết kiệm vài khối lệnh.

## 10. Quy trình refactor và tự luyện tập

Khi gặp một chuỗi `if` lồng sâu, làm theo trình tự:

1. **Viết rõ hợp đồng đầu vào/đầu ra**: những điều kiện nào phải đúng, dữ liệu nào có thể `null`, điều gì xảy ra nếu không khớp?
2. **Nhận diện các kiểm tra cấu trúc**: `instanceof` và accessor liên tiếp trên các record có thể gộp thành type pattern hoặc record pattern.
3. **Đưa đường đi thất bại ra sớm** bằng guard clause khi nó không có xử lý đặc biệt.
4. **Ghép điều kiện độc lập bằng `&&`**, giữ thứ tự an toàn với `null` và bảo đảm phạm vi biến mẫu.
5. **Tách các quy tắc nghiệp vụ dài** thành hàm có tên rõ, không ép mọi logic vào một biểu thức.
6. **Dùng `switch` khi có nhiều trường hợp/kết quả**, đặt nhánh cụ thể trước nhánh bao quát.
7. **Đối chiếu hành vi trước và sau** trên ca hợp lệ, sai kiểu, thiếu dữ liệu, ranh giới giá trị, trạng thái không phù hợp và `null`.

Bài tập: thử thay điều kiện `total >= 100` bằng `total >= 200`, giữ nguyên 11 ca kiểm thử ban đầu. Ca `eligible` có tổng 150 và `boundary-100` có tổng 100 phải không còn đạt; hãy cập nhật kỳ vọng hoặc tạo test riêng cho ngưỡng 200. Sau đó thử thêm một trạng thái `"REFUNDED"` và xác minh cả bốn phương thức boolean lẫn `switch` đều từ chối trạng thái ấy.

**Ghi nhớ:** Để tránh điều kiện lồng quá sâu khi kết hợp patterns, hãy dùng pattern matching để kiểm tra **hình dạng dữ liệu**, guard clause để thoát sớm, `&&` để kết hợp quy tắc theo thứ tự an toàn, hàm phụ trợ để đặt tên cho logic nghiệp vụ và `switch` cho những kết quả khác nhau. Điều quan trọng nhất là **giảm độ phức tạp đọc hiểu mà vẫn giữ nguyên hành vi trên cả ca đúng lẫn ca sai**.