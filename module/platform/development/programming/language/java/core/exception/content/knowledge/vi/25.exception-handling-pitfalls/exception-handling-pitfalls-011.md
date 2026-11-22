# Bắt lỗi do sai lập trình rồi tiếp tục với trạng thái không hợp lệ

Trong Java, `catch` cho phép chương trình xử lý một ngoại lệ. Tuy nhiên, **bắt được ngoại lệ không có nghĩa chương trình đã phục hồi**. Một sai lầm nguy hiểm là bắt `NullPointerException`, `IllegalStateException`, `IndexOutOfBoundsException` hoặc một `RuntimeException` khác do lỗi lập trình, ghi một dòng log (hoặc bỏ qua), rồi vẫn tiếp tục cập nhật dữ liệu hay thông báo thành công như thể mọi điều kiện ban đầu còn đúng.

Hệ quả thường nghiêm trọng hơn lỗi đầu tiên: đối tượng có thể chỉ được cập nhật một nửa, đơn hàng chuyển sang trạng thái “đã xác nhận” dù chưa được xử lý, bộ đếm hoặc số dư mất cân bằng, giao dịch bị lặp lại, hoặc lỗi thực bị che bởi một ngoại lệ xuất hiện muộn hơn.

Nguyên tắc cốt lõi: **chỉ tiếp tục khi đã chứng minh được trạng thái sau lỗi vẫn hợp lệ và có một chiến lược phục hồi thực sự**. Nếu lỗi chứng tỏ một bất biến (*invariant*) hoặc giả định của chương trình đã bị phá vỡ, thường cần dừng thao tác hiện tại, chuyển thất bại đến ranh giới xử lý thích hợp và đưa trạng thái về một điểm nhất quán.

## 1. Phân biệt “đã bắt lỗi” với “đã phục hồi”

Xét một chuỗi thao tác:

```text
Bắt đầu yêu cầu
    |
    v
Đổi trạng thái A
    |
    v
Gặp lỗi lập trình tại bước B
    |
    +--> catch (RuntimeException error)
              |
              +--> bỏ qua / log rồi tiếp tục
                        |
                        v
               Đổi trạng thái C
                        |
                        v
              Trả kết quả thành công  <-- nguy hiểm
```

Bản thân `catch` chỉ chuyển điều khiển vào một nhánh xử lý. Nó **không tự hoàn tác** những thay đổi đã thực hiện trước ngoại lệ, không tự trả khóa hay hủy giao dịch nghiệp vụ, cũng không xác nhận rằng biến và tài nguyên đang ở trạng thái đúng.

Một hướng xử lý đúng phải trả lời được:

1. Lỗi là tình huống **được hợp đồng dự kiến** hay là dấu hiệu của bug?
2. Những thay đổi nào đã được thực hiện trước lúc lỗi xảy ra?
3. Có thể hoàn tác, hủy giao dịch hoặc chuyển sang trạng thái thất bại hợp lệ không?
4. Tác vụ có được phép trả fallback, thử lại hoặc tiếp tục với dữ liệu hiện có không?
5. Bằng cách nào tầng gọi biết một yêu cầu đã thất bại và không được coi là thành công?

Nếu chưa thể trả lời các câu hỏi trên, không nên dùng `catch` như một lối đi tắt để “cho chương trình chạy tiếp”.

## 2. Thế nào là lỗi do sai lập trình?

Một số ngoại lệ thường gợi ý giả định trong mã đã bị vi phạm:

| Ngoại lệ thường gặp | Ví dụ nguyên nhân | Điều cần kiểm tra |
| --- | --- | --- |
| `NullPointerException` | Mã truy cập đối tượng mà hợp đồng nội bộ yêu cầu không được `null` | Dữ liệu từ đâu ra, kiểm tra null ở đúng ranh giới chưa, biến có bị khởi tạo sai không |
| `IndexOutOfBoundsException` | Truy cập phần tử không tồn tại; giả định danh sách có đủ phần tử | Kích thước danh sách, vòng lặp, điều kiện biên |
| `ClassCastException` | Ép kiểu không đúng kiểu thực tế | Thiết kế kiểu dữ liệu, generics, hợp đồng đầu vào |
| `IllegalStateException` | Thao tác diễn ra khi đối tượng đang ở trạng thái không cho phép | Bất biến, thứ tự chuyển trạng thái và trách nhiệm sở hữu |
| `IllegalArgumentException` | Truyền đối số trái hợp đồng | Đây là lỗi bên gọi, hay đầu vào bên ngoài cần trả phản hồi hợp lệ? |
| `ArithmeticException` | Ví dụ chia số nguyên cho 0 | Điều kiện toán học, dữ liệu và nhánh tính toán |
| `AssertionError` | Một khẳng định nội bộ thất bại khi assertions được bật | Bất biến thiết kế; không biến nó thành thành công giả |

**Phân loại phải dựa trên hợp đồng, không chỉ tên lớp.** `NumberFormatException` là một `IllegalArgumentException`, nhưng khi parse văn bản do người dùng nhập, chuỗi sai định dạng có thể là tình huống *dự kiến* cần trả lỗi kiểm tra đầu vào. Ngược lại, `NullPointerException` ở giữa một thuật toán với tham số đã được kiểm tra có thể là bug thực sự.

`RuntimeException` là ngoại lệ unchecked; **unchecked không đồng nghĩa không được phép bắt**, cũng không đồng nghĩa mọi trường hợp đều là lỗi lập trình. Điểm quan trọng là phải có chiến lược xử lý tương ứng với nguyên nhân và trạng thái còn lại.

`Error` như `OutOfMemoryError`, `StackOverflowError` nói chung không thuộc nhóm ngoại lệ nghiệp vụ có thể phục hồi bằng cách bắt rộng và tiếp tục. Đặc biệt tránh `catch (Throwable error)` chỉ để bỏ qua mọi lỗi.

## 3. Bất biến và trạng thái nửa vời (*partial mutation*)

**Bất biến** là điều kiện phải đúng mỗi khi đối tượng ở một trạng thái được công bố là hợp lệ.

Ví dụ một kho giả định có tổng 5 đơn vị hàng:

\[
\text{available} + \text{reserved} = 5
\]

Một thao tác đặt trước 2 đơn vị hợp lệ sẽ chuyển từ `(available=5, reserved=0)` sang `(available=3, reserved=2)`. Nếu mã sửa `available` trước, rồi mới phát hiện đối số không hợp lệ và **nuốt ngoại lệ**, bất biến có thể bị phá vỡ.

Đoạn sai về ý tưởng:

```java
try {
    inventory.available -= quantity;
    if (quantity <= 0) {
        throw new IllegalArgumentException("quantity must be positive");
    }
    inventory.reserved += quantity;
} catch (IllegalArgumentException error) {
    // Bỏ qua; trường available đã bị sửa.
}
```

Đây là **mã minh họa** yêu cầu đối tượng `inventory` và biến `quantity` do ứng dụng khai báo, không phải chương trình độc lập. Với `quantity = -2`, phép trừ đã làm `available` **tăng** 2 trước khi ngoại lệ được ném. Nhánh `catch` không tự khôi phục số liệu.

Càng nguy hiểm nếu phía dưới còn đặt cờ `confirmed=true`, gửi sự kiện hoặc phát hành phản hồi HTTP `200 OK`: các hệ thống khác có thể hành động dựa trên **thành công giả**.

## 4. Ví dụ Java 17+ chạy được: catch rồi tiếp tục làm hỏng trạng thái

Tạo tệp **`InvalidStateAfterCatch.java`**:

```java
public class InvalidStateAfterCatch {
    static final class Inventory {
        final int capacity = 5;
        int available = 5;
        int reserved = 0;
        boolean confirmed;

        boolean invariantHolds() {
            return available >= 0
                    && reserved >= 0
                    && available + reserved == capacity;
        }
    }

    static void reserveWrong(Inventory inventory, int quantity) {
        try {
            inventory.available -= quantity; // Thay đổi trước khi kiểm tra.
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }
            inventory.reserved += quantity;
            inventory.confirmed = true;
        } catch (IllegalArgumentException ignored) {
            // Sai: đánh dấu thành công mặc dù trạng thái đã bị sửa dở.
            inventory.confirmed = true;
        }
    }

    static void reserveCorrect(Inventory inventory, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }
        if (quantity > inventory.available) {
            throw new IllegalStateException("insufficient stock");
        }

        int nextAvailable = inventory.available - quantity;
        int nextReserved = inventory.reserved + quantity;
        if (nextAvailable < 0
                || nextReserved < 0
                || nextAvailable + nextReserved != inventory.capacity) {
            throw new IllegalStateException("inventory invariant broken");
        }

        inventory.available = nextAvailable;
        inventory.reserved = nextReserved;
        inventory.confirmed = true;
    }

    static void print(String label, Inventory inventory) {
        System.out.println(label + " available=" + inventory.available
                + " reserved=" + inventory.reserved
                + " confirmed=" + inventory.confirmed
                + " valid=" + inventory.invariantHolds());
    }

    public static void main(String[] args) {
        Inventory wrong = new Inventory();
        reserveWrong(wrong, -2);
        print("wrong", wrong);

        Inventory correct = new Inventory();
        try {
            reserveCorrect(correct, -2);
        } catch (IllegalArgumentException error) {
            System.out.println("rejected="
                    + error.getClass().getSimpleName());
        }
        print("afterReject", correct);

        reserveCorrect(correct, 2);
        print("afterSuccess", correct);
    }
}
```

Biên dịch, chạy với Java 17:

```bash
javac --release 17 InvalidStateAfterCatch.java
java InvalidStateAfterCatch
```

Đầu ra chính xác:

```text
wrong available=7 reserved=0 confirmed=true valid=false
rejected=IllegalArgumentException
afterReject available=5 reserved=0 confirmed=false valid=true
afterSuccess available=3 reserved=2 confirmed=true valid=true
```

**Phân tích:**

- `reserveWrong(..., -2)` thay đổi `available` thành `7`, sau đó mới phát hiện đối số sai. Ngoại lệ bị nuốt và `confirmed=true`. Tổng `available + reserved = 7` trái với `capacity=5`: mã đã báo thành công trong trạng thái không hợp lệ.
- `reserveCorrect(..., -2)` kiểm tra điều kiện trước mọi thay đổi. Lỗi được truyền tới tầng gọi, đối tượng giữ nguyên `(5,0,false)` và bất biến đúng.
- `reserveCorrect(..., 2)` tính giá trị dự kiến, kiểm tra bất biến rồi mới công bố thay đổi, cho kết quả `(3,2,true)`.

Ví dụ trên là mô hình **đơn luồng với các trường nằm trong bộ nhớ**. Nó chứng minh ý tưởng kiểm tra trước khi sửa, **không phải giao dịch nguyên tử** cho nhiều luồng hoặc hệ thống phân tán. Nếu có truy cập đồng thời, cần đồng bộ/atomic state phù hợp. Nếu đã gọi cơ sở dữ liệu hoặc dịch vụ ngoài, còn cần transaction, cơ chế hủy hoặc bù trừ thực tế.

## 5. Phục hồi thật sự cần những điều kiện nào?

Một nhánh `catch` có thể tiếp tục khi nó **biết rõ lỗi gì**, **có thể làm gì sau lỗi** và **duy trì các bất biến**.

Ví dụ các tình huống có thể được hợp đồng cho phép:

- Người dùng nhập số không đúng định dạng: bắt `NumberFormatException`, trả phản hồi yêu cầu sửa đầu vào, không cập nhật trạng thái nghiệp vụ.
- Một cache không sẵn sàng nhưng nguồn chính vẫn hoạt động: ghi cảnh báo, đọc từ nguồn chính, kiểm soát tác dụng phụ để tránh kết quả trùng.
- Đọc một tệp cấu hình tùy chọn không thành công: chọn mặc định được tài liệu hóa nếu mặc định đó **thực sự hợp lệ** với ứng dụng.
- Một thao tác được thiết kế idempotent thất bại tạm thời: có thể thử lại với giới hạn thời gian/số lần thử, nhưng phải kiểm tra lỗi, tài nguyên và tính an toàn của retry.

Ngược lại, nếu `IllegalStateException` chỉ ra số lượng đặt trước và tồn kho mất cân bằng, việc ghi log rồi tiếp tục “bán hàng” **không phải phục hồi**. Muốn phục hồi cần sửa hoặc tái dựng trạng thái theo quy tắc đã được kiểm chứng, không gán ngẫu nhiên một giá trị để vượt qua điều kiện kiểm tra.

Một bộ tiêu chí ngắn cho nhánh phục hồi:

1. **Ngoại lệ dự kiến và được phân loại hẹp.** Không dùng `catch (Exception ignored)` thay cho hợp đồng lỗi.
2. **Không có tác dụng phụ không được kiểm soát.** Những thay đổi trước lỗi đã được hoàn tác, bù trừ hoặc tồn tại trong một trạng thái thất bại được thiết kế rõ.
3. **Đầu ra trung thực.** Nếu chưa hoàn thành thao tác, không trả về kết quả báo “đã hoàn thành”.
4. **Có quan sát và kiểm thử.** Log/metric phản ánh việc dùng fallback hoặc retry; test kiểm tra cả trạng thái sau lỗi.
5. **Có giới hạn.** Nếu việc thử lại thất bại liên tiếp, dừng và chuyển lỗi lên thay vì tạo vòng lặp vô hạn.

## 6. Bắt đúng loại lỗi thay vì `catch (RuntimeException)` rồi mặc định thành công

Một lỗi phổ biến khác: dùng một `catch` quá rộng cho cả input không hợp lệ **và** bug.

```java
String parseWrong(String raw) {
    try {
        int quantity = Integer.parseInt(raw.trim());
        return "accepted:" + quantity;
    } catch (RuntimeException ignored) {
        return "accepted:0";
    }
}
```

Đoạn trên là một **phương thức minh họa**, không phải chương trình độc lập. Nó bắt cả `NumberFormatException` lẫn `NullPointerException` từ `raw.trim()`, rồi trả về một kết quả trông hợp lệ. Nếu một tầng nội bộ có hợp đồng `raw` không được `null`, caller vừa vi phạm hợp đồng nhưng sự cố bị biến thành “đã chấp nhận 0”.

Ở ranh giới nhận input từ bên ngoài, `null` cũng có thể là **input dự kiến cần từ chối**. Khi đó hãy kiểm tra rõ ràng ở bước validation, không để một `NullPointerException` tình cờ làm giao thức phân loại đầu vào.

### Ví dụ thứ hai: phân loại hẹp và dừng request sai hợp đồng

Tạo tệp **`NarrowCatchBoundary.java`**:

```java
import java.util.Objects;

public class NarrowCatchBoundary {
    static String wrong(String raw) {
        try {
            return "accepted:" + Integer.parseInt(raw.trim());
        } catch (RuntimeException ignored) {
            return "accepted:0";
        }
    }

    static String correct(String nonNullRaw) {
        Objects.requireNonNull(nonNullRaw, "nonNullRaw");
        try {
            return "accepted:" + Integer.parseInt(nonNullRaw);
        } catch (NumberFormatException expected) {
            return "invalid number";
        }
    }

    public static void main(String[] args) {
        System.out.println("wrongNull=" + wrong(null));
        System.out.println("valid=" + correct("5"));
        System.out.println("badFormat=" + correct("oops"));

        try {
            correct(null);
        } catch (NullPointerException unexpected) {
            System.out.println("requestFailed="
                    + unexpected.getClass().getSimpleName());
        }
    }
}
```

Chạy:

```bash
javac --release 17 NarrowCatchBoundary.java
java NarrowCatchBoundary
```

Đầu ra:

```text
wrongNull=accepted:0
valid=accepted:5
badFormat=invalid number
requestFailed=NullPointerException
```

Trong `correct`, `nonNullRaw` là **hợp đồng nội bộ**. Sai định dạng (`"oops"`) là tình huống mà phương thức chủ động phân loại và trả về `"invalid number"`; truyền `null` trái hợp đồng, nên `Objects.requireNonNull` báo lỗi và thao tác không giả vờ thành công. `main` đóng vai trò **ranh giới của bản demo**: bắt lỗi bất ngờ để minh họa rằng request bị thất bại; mã nghiệp vụ bên trong không tiếp tục.

Lưu ý: ví dụ trả các chuỗi chỉ để dễ quan sát. Trong ứng dụng thực, nên dùng kiểu kết quả rõ ràng (ví dụ `Result`, enum/mã lỗi, HTTP 400 với input sai, HTTP 500 với bug nội bộ), thay vì buộc người gọi phân tích chuỗi tiếng Anh.

## 7. Vì sao tiếp tục sau lỗi lập trình dễ gây lỗi dây chuyền?

Giả sử một chương trình có chuỗi trạng thái:

```text
CREATED -> VALIDATED -> RESERVED -> PAID -> CONFIRMED
```

Nếu bước `RESERVED` ném `IllegalStateException` vì mất cân bằng số lượng, nhưng catch lại đổi trạng thái thành `PAID`, các bước sau có thể:

- Trừ tiền khi chưa khóa tài nguyên/sản phẩm.
- Phát sự kiện cho hệ thống giao nhận dựa trên đơn hàng chưa đặt thành công.
- Ghi bảng lịch sử “đã thanh toán” nhưng bảng nghiệp vụ chính vẫn ở trạng thái “mới tạo”.
- Thực hiện retry từ tầng ngoài, trong khi một phần tác dụng phụ của lần thử đầu đã xảy ra.
- Gây thêm `NullPointerException` hoặc `ClassCastException` về sau, che mất lỗi ban đầu.

Lỗi thứ hai thường xuất hiện **xa nơi lỗi đầu tiên**, nên stack trace của nó khó giải thích nguyên nhân gốc. Giữ và chuyển lỗi đầu tiên tới ranh giới xử lý sẽ rút ngắn đường chẩn đoán.

Hãy thiết kế chuyển trạng thái theo những điểm công bố rõ ràng. Nếu chưa hoàn thành tất cả bước cần thiết, không chuyển đối tượng sang trạng thái cho phép bước tiếp theo. Khi việc thực thi có tác dụng phụ từ xa, trạng thái trung gian như `PENDING`, `FAILED` hoặc `REQUIRES_RECONCILIATION` có thể cần thiết; không đơn giản “quay lại ban đầu” khi kết quả thực tế bên ngoài chưa rõ.

## 8. Fail fast: dừng đúng phạm vi, không nhất thiết dừng toàn JVM

**Fail fast** nghĩa là phát hiện sự vi phạm giả định càng sớm càng tốt và **không tiếp tục dùng dữ liệu đã mất tính tin cậy**. Nó không có nghĩa luôn gọi `System.exit`, tắt toàn bộ JVM hoặc để mọi request khiến service chết.

Ví dụ trong web service:

1. Tầng xử lý phát hiện `IllegalStateException` không thể sửa.
2. Thao tác nghiệp vụ hiện tại dừng; transaction được đánh dấu rollback khi có transaction thích hợp.
3. Bộ xử lý lỗi ở ranh giới request ghi log cả `Throwable` với mã tương quan an toàn.
4. Người gọi nhận kết quả thất bại trung thực; hệ thống không công bố “thành công”.
5. Worker/request khác có trạng thái cô lập vẫn được phục vụ nếu nền tảng còn an toàn.

Nếu lỗi phá vỡ **bất biến toàn cục** hoặc làm thành phần không còn đáng tin (ví dụ bộ nhớ dùng chung bị hỏng), hành động có thể phải nghiêm khắc hơn: đưa thành phần ra khỏi lưu lượng, từ chối tác vụ mới hoặc khởi động lại có kiểm soát. Nhưng quyết định đó cần dựa trên mức lan truyền của sai lệch, không phải chỉ trên việc nhìn thấy một `RuntimeException`.

Nếu một request thất bại mà chưa có thay đổi dữ liệu, việc trả lỗi là đủ. Nếu dữ liệu đã bị sửa một phần, **trả lỗi không tự sửa dữ liệu**: còn cần rollback, phục hồi hoặc cách ly.

## 9. Transaction, rollback và các tác dụng phụ bên ngoài

Để tránh trạng thái nửa vời, thứ tự xử lý nên là:

```text
Validate input và invariant
        |
        v
Tính toán trạng thái dự kiến
        |
        v
Bắt đầu đơn vị công việc có thể rollback / transaction
        |
        v
Thực hiện thay đổi thuộc cùng ranh giới nguyên tử
        |
        +-- lỗi --> rollback / đánh dấu FAILED / bù trừ
        |
        v
Commit hoặc công bố hoàn tất
```

Đây là sơ đồ khái niệm, không cam kết rằng mọi tác dụng phụ đều thuộc một transaction.

**Đối với bộ nhớ đơn luồng:** có thể kiểm tra trước, tính các giá trị mới vào biến cục bộ rồi mới gán cho đối tượng. Nếu cập nhật nhiều đối tượng hoặc chạy nhiều luồng, cần giải pháp đồng bộ/atomic phù hợp; vài lệnh gán liên tiếp không tự trở thành nguyên tử.

**Đối với cơ sở dữ liệu:** sử dụng transaction có ranh giới rõ, rollback khi thất bại theo cấu hình công nghệ đang dùng. Không giả định `catch` rồi trả về thành công khiến framework vẫn rollback; trong một số framework, việc nuốt ngoại lệ làm transaction trông như đã hoàn tất bình thường.

**Đối với HTTP, thanh toán, message queue:** một thao tác bên ngoài có thể đã hoàn thành dù client nhận timeout/lỗi. Rollback cơ sở dữ liệu cục bộ không xóa được tác dụng phụ ở bên ngoài. Khi cần, thiết kế idempotency key, outbox, saga/compensating action hoặc trạng thái đối soát. Không retry bừa chỉ vì đã “bắt được lỗi”.

**Đối với tài nguyên:** dùng `try-with-resources` và `finally` để đóng những tài nguyên thuộc quyền sở hữu; đừng coi giải phóng tài nguyên là giấy phép tiếp tục nghiệp vụ với dữ liệu không hợp lệ.

## 10. Bắt lỗi ở ranh giới phù hợp và giữ nguyên nhân

Khi bug hoặc bất biến hỏng, hãy giữ thông tin để điều tra.

Ví dụ minh họa với SLF4J, không phải chương trình Java độc lập (`logger`, `requestId`, `service` được ứng dụng cung cấp):

```java
try {
    service.execute();
} catch (IllegalStateException error) {
    logger.error("Request {} failed with invalid state", requestId, error);
    throw error;
}
```

Đoạn trên ghi **đối tượng `Throwable`** thay vì chỉ `error.getMessage()`, và chuyển tiếp lỗi. Trong service nhiều tầng, tránh log cùng stack trace ở mọi tầng; nên xác định ai sở hữu logging ở ranh giới cuối để giảm log trùng.

Nếu cần chuyển sang loại lỗi có nghĩa hơn, **giữ cause**:

```java
try {
    repository.save(order);
} catch (java.io.IOException cause) {
    throw new IllegalStateException("Cannot persist order", cause);
}
```

Đây là mã minh họa cần `repository`, `order`. `cause` cho phép theo dấu lỗi gốc; `throw new IllegalStateException(cause.getMessage())` sẽ làm mất chuỗi nguyên nhân. Tuy nhiên, đừng bọc `IllegalStateException` không thể phục hồi thành một mã “người dùng nhập sai” nếu bản chất là bug nội bộ.

Trong một bộ xử lý lỗi toàn cục, có thể chuyển lỗi sang cấu trúc phản hồi **không chứa stack trace** cho người dùng và ghi chi tiết nội bộ bằng logger. Tránh để password, token, dữ liệu cá nhân hoặc nội dung input tùy ý lọt vào message/log.

## 11. `finally` và `try-with-resources` không có nghĩa được tiếp tục

`finally` thường chạy trên đường thoát của `try`/`catch`, kể cả khi có lỗi, nhưng **cleanup không phải phục hồi trạng thái nghiệp vụ**:

```java
try {
    persistBusinessChanges();
} catch (RuntimeException error) {
    logger.error("Persistence failed", error);
} finally {
    notifySuccess(); // Sai: vẫn chạy khi ghi dữ liệu lỗi.
}
```

Đây là mảnh minh họa có các phương thức/logger của ứng dụng. Chỉ phát sự kiện thành công sau khi thao tác thực sự hoàn tất hoặc commit. `try-with-resources` có thể đóng tài nguyên và giữ suppressed exceptions khi `close()` lỗi nhưng **không tự rollback tác dụng phụ**.

Ở bài này, việc dừng xử lý trạng thái **bất hợp lệ** là trọng tâm; cơ chế ưu tiên exception khi `finally` ném lỗi hoặc `close()` thất bại được trình bày trong các bài cleanup riêng.

## 12. Những `catch` quá rộng làm lỗi bị che khuất

Những mẫu đáng cảnh giác:

```java
catch (Exception ignored) {
    return null;
}
```

```java
catch (RuntimeException error) {
    return true;
}
```

```java
catch (Throwable error) {
    continue;
}
```

Đây là **các mảnh mã phản ví dụ**, không phải khối Java độc lập. Trong mỗi trường hợp, caller không thể phân biệt một hoạt động thành công với tình huống lỗi bị che; đặc biệt `catch (Throwable)` còn gồm `Error`, thường không nên coi là tín hiệu có thể xử lý như lỗi nghiệp vụ thông thường.

Trong vòng lặp xử lý hàng loạt, có thể có lý do **bỏ qua một bản ghi không hợp lệ**, nhưng phải giới hạn lỗi, cách ly bản ghi, ghi nhận thất bại và tiếp tục **với trạng thái được thiết kế cho việc bỏ qua đó**. Không bắt tất cả ngoại lệ rồi tiếp tục dùng chính object đang nghi hỏng.

Ví dụ một batch có thể phân loại lỗi định dạng cho **từng dòng độc lập**, ghi kết quả `INVALID_INPUT` cho dòng đó rồi xử lý dòng tiếp theo. Nhưng nếu một `NullPointerException` bất ngờ cho thấy bộ parser đang giữ trạng thái dùng chung bị lỗi, tiếp tục toàn batch có thể nhân rộng dữ liệu sai. Ranh giới cách ly quyết định hành vi phù hợp.

## 13. Các tác vụ bất đồng bộ và exception bị nuốt

Trong `ExecutorService` hoặc `CompletableFuture`, lỗi do sai lập trình có thể phát sinh ở worker nhưng chỉ được quan sát qua `Future.get()` hoặc `CompletableFuture.join()`.

Ví dụ minh họa:

```java
CompletableFuture<Order> result =
        CompletableFuture.supplyAsync(() -> processOrder(order));
```

Đây là mảnh mã cần khai báo `Order`, `order` và `processOrder`. Nếu lambda ném `IllegalStateException` thì future có thể hoàn tất thất bại. Nhưng nếu lambda tự bắt `RuntimeException`, trả `Order` giả thành công hoặc chuyển `confirmed=true`, future sẽ được xem là **hoàn tất bình thường**, làm người gọi không còn biết vấn đề.

Với `CompletableFuture`, `exceptionally(error -> fallback)` có thể chủ đích biến thất bại thành giá trị thành công. Chỉ làm vậy khi fallback **được cho phép bởi hợp đồng** và không che một bug làm dữ liệu mất nhất quán. Không đặt `exceptionally(error -> new Order("SUCCESS"))` trên mọi pipeline để chống lỗi chung.

Tương tự, `Future.isDone()` và `CompletableFuture.isDone()` chỉ nói rằng future đã hoàn tất (có thể bình thường, lỗi hoặc hủy), không chứng minh thay đổi nghiệp vụ đã thành công. Khi `join()` ném `CompletionException` hoặc `get()` ném `ExecutionException`, cần truy cause để tìm sự cố thật, không bắt lớp bọc rồi tự ý coi request đã xử lý xong.

## 14. Retry và fallback chỉ an toàn khi có điều kiện

Một lỗi tạm thời của dịch vụ ngoài có thể được retry, nhưng một lỗi lập trình như truy cập index sai, cast sai hoặc invariant hỏng thường **không biến mất** nhờ lặp lại với cùng dữ liệu. Retry vô điều kiện có thể tăng tải, tạo thao tác trùng và che lỗi.

Trước khi retry cần có:

- Loại lỗi hoặc mã trạng thái được xác định là tạm thời.
- Tác vụ được xác nhận an toàn để chạy lại hoặc có khóa idempotency.
- Chính sách giới hạn số lần thử, khoảng chờ, tổng deadline.
- Trạng thái sau lần thất bại trước được xác nhận hợp lệ.
- Log/metric để phân biệt lần thử lại với một thành công thật.

Fallback cũng vậy. Một cache lỗi nhưng nguồn chính còn tốt có thể trả dữ liệu từ nguồn chính; ngược lại, lỗi làm dữ liệu định giá không nhất quán không thể sửa bằng cách trả giá trị `0` rồi ghi đơn hàng thành công.

Nếu không chứng minh được tính an toàn của retry/fallback, cần **đưa thất bại lên tầng có thể quyết định** thay vì tự phục hồi một cách giả tạo.

## 15. Kiểm thử đường lỗi và bất biến, không chỉ kiểm tra ngoại lệ

Test tốt không chỉ xác nhận `"method threw IllegalArgumentException"`, mà còn xác nhận **đối tượng sau lỗi vẫn hợp lệ**, side effect đúng và caller nhận thất bại.

Với ví dụ `Inventory`, các kịch bản cần kiểm tra:

| Kịch bản | Kỳ vọng về lỗi/kết quả | Kỳ vọng về trạng thái |
| --- | --- | --- |
| `quantity = -2` | Từ chối `IllegalArgumentException` | Giữ `(available=5, reserved=0, confirmed=false)` |
| `quantity = 0` | Từ chối như input không hợp lệ | Không thay đổi dữ liệu |
| `quantity > available` | Không cho đặt trước | Không tạo lượng hàng âm hay tăng `reserved` |
| `quantity = 2` | Thành công | `(available=3, reserved=2, confirmed=true)` |
| Bug giữa thao tác sau khi có side effect | Request thất bại | Rollback, bù trừ, hoặc trạng thái FAILED rõ ràng |
| Hai thao tác đồng thời | Không vi phạm capacity | Bảo vệ tính nhất quán bằng cơ chế đồng bộ/transaction |

Trong JUnit 5 (đoạn minh họa cần import JUnit và khai báo lớp/trạng thái tương ứng), có thể viết:

```java
assertThrows(IllegalArgumentException.class,
        () -> reserveCorrect(state, -2));
assertEquals(5, state.available);
assertEquals(0, state.reserved);
assertFalse(state.confirmed);
assertTrue(state.invariantHolds());
```

Đây **không phải chương trình độc lập**; `assertThrows`, `assertEquals`, `assertFalse`, `assertTrue` là API JUnit 5. Java 17 không tích hợp sẵn JUnit. Mục đích là kiểm thử **đường lỗi và tính bất biến**, chứ không chỉ kiểm tra rằng một exception được ném.

Nếu mã cần rollback transaction, test tích hợp nên xác nhận dữ liệu DB không bị commit sau lỗi. Nếu có các thao tác bên ngoài, cần test kết quả retry, idempotency hoặc đối soát; một unit test trên object bộ nhớ chưa bao phủ toàn bộ tác dụng phụ.

## 16. Phân biệt bắt ở ranh giới request và nuốt lỗi trong nghiệp vụ

Một service có thể dùng bộ xử lý lỗi toàn cục để biến exception thành HTTP 500 hoặc một thông báo lỗi an toàn. Về cú pháp, đó vẫn là “bắt lỗi”; nhưng khác cơ bản với việc **nuốt lỗi ở giữa luồng nghiệp vụ**.

| Bắt ở tầng nghiệp vụ rồi chạy tiếp | Bắt ở ranh giới để kết thúc yêu cầu |
| --- | --- |
| Có thể giữ state không hợp lệ cho các bước sau | Không chạy các bước tiếp theo của yêu cầu thất bại |
| Dễ trả về thành công giả | Trả kết quả thất bại trung thực |
| Không tự rollback | Có thể kết hợp transaction rollback và phục hồi theo hợp đồng |
| Thường che nguyên nhân gốc | Có thể ghi `Throwable` và correlation ID |
| Rất khó phân biệt retry an toàn | Tầng điều phối có thể quyết định retry/fail dựa trên nguyên nhân |

Bắt ở tầng cuối **không tự sửa state đã bị thay đổi**: cần xác định boundary transaction, tài nguyên và cách xử lý side effect. Nhưng nó giữ được nguyên tắc không cho bước nghiệp vụ sau tiếp tục với dữ liệu sai.

Nếu một service đa tenant gặp bug chỉ trong một request, nên cách ly thất bại ở request hoặc worker tương ứng, giữ hoạt động khác không liên quan khi an toàn. Nếu một bất biến của state toàn cục đã hỏng, phải đánh giá sức khỏe toàn thành phần thay vì tiếp tục mù quáng.

## 17. Những lỗi thường gặp khi review mã

| Mẫu sai | Nguy cơ | Thay thế phù hợp |
| --- | --- | --- |
| `catch (NullPointerException e) {}` | Che lỗi giả định null, phần xử lý tiếp tục với dữ liệu chưa chắc đúng | Làm rõ hợp đồng null, sửa nguồn lỗi; thất bại nếu invariant không bảo đảm |
| `catch (RuntimeException e) { return true; }` | Trả thành công giả | Trả kết quả thất bại hoặc ném tiếp; chỉ fallback với lỗi dự kiến |
| Sửa object rồi mới kiểm tra điều kiện và nuốt lỗi | Trạng thái cập nhật một phần | Validate trước, tính state mới, commit tại điểm an toàn |
| `catch (Exception e)` chỉ để `System.out.println(e.getMessage())` | Lỗi bị che, mất stack/cause | Ghi đối tượng `Throwable` ở ranh giới xử lý và truyền thất bại |
| `finally { markSuccess(); }` | Đánh dấu thành công cả khi lỗi | Chỉ đánh dấu sau bước commit thành công |
| Bắt `Throwable` để ứng dụng “không bao giờ lỗi” | Có thể nuốt `Error` nghiêm trọng | Không bắt quá rộng; chỉ bắt tại ranh giới đủ trách nhiệm |
| Retry tất cả `IllegalStateException` | Bug lặp lại, tăng side effect | Chỉ retry lỗi tạm thời đã phân loại và an toàn |
| `exceptionally(e -> successValue)` cho mọi lỗi | `CompletableFuture` báo thành công dù bug | Chỉ phục hồi loại lỗi/case được hợp đồng cho phép |
| Test chỉ `assertThrows` nhưng không kiểm tra state | Không phát hiện partial mutation | Khẳng định cả trạng thái, giao dịch và side effect |
| Bắt ngoại lệ xong bỏ qua interrupted status | Không đáp ứng tín hiệu hủy hợp tác | Xử lý/khôi phục ngắt theo hợp đồng công việc |

## 18. Tự kiểm tra

**Câu 1.** Sau khi cập nhật một nửa object, phương thức ném `IllegalStateException`. Bắt rồi ghi log có tự khôi phục object không?  
**Đáp án:** Không. `catch` chỉ chuyển điều khiển. Cần rollback, bù trừ hoặc không công bố state không hợp lệ.

**Câu 2.** `NullPointerException` luôn là lỗi lập trình không được bắt?  
**Đáp án:** Không thể kết luận chỉ từ tên lớp. Nhưng nếu nó phản ánh giả định nội bộ bị vi phạm, việc nuốt lỗi rồi tiếp tục thường nguy hiểm. Kiểm tra input ở ranh giới và dùng chính sách lỗi rõ ràng.

**Câu 3.** Một parser bắt `NumberFormatException` và trả `INVALID_INPUT` cho người dùng có hợp lệ không?  
**Đáp án:** Có thể hợp lệ nếu chuỗi sai định dạng là tình huống dự kiến, trạng thái chưa bị cập nhật và caller nhận kết quả lỗi rõ ràng.

**Câu 4.** Vì sao `catch (RuntimeException error) { return 0; }` có thể che bug?  
**Đáp án:** Vì nhiều lỗi không liên quan, như `NullPointerException` và `IndexOutOfBoundsException`, đều thuộc `RuntimeException`. Trả 0 khiến caller không biết có sự cố bất ngờ.

**Câu 5.** `finally` có phù hợp để đặt `order.confirmed = true` không?  
**Đáp án:** Không, vì `finally` còn chạy khi thao tác thất bại. Nó phù hợp cho dọn dẹp, không phải xác nhận thành công vô điều kiện.

**Câu 6.** `CompletableFuture.exceptionally(e -> fallback)` có nguy cơ gì?  
**Đáp án:** Nó có thể biến cả bug thành kết quả hoàn tất bình thường. Chỉ dùng fallback khi biết trạng thái và loại lỗi cho phép.

**Câu 7.** Bắt lỗi tại controller rồi trả HTTP 500 có giống nuốt lỗi trong service không?  
**Đáp án:** Không. Controller có thể kết thúc request bằng thất bại trung thực; service nuốt lỗi rồi tiếp tục thì có thể gây corruption. Dù vậy controller vẫn cần transaction/compensation thích hợp nếu state đã sửa.

**Câu 8.** Trường hợp nào nên chủ động cho worker khác tiếp tục?  
**Đáp án:** Khi các worker có trạng thái được cách ly và sự cố không làm hỏng bất biến chung; worker thất bại phải được đánh dấu và xử lý riêng.

**Câu 9.** Một lỗi mạng có chắc retry an toàn không?  
**Đáp án:** Không. Phải xem request đã tạo side effect chưa, lỗi có tạm thời không, và có idempotency hay đối soát không.

**Câu 10.** Sau khi bắt exception, điều kiện tối thiểu để tiếp tục là gì?  
**Đáp án:** Có chính sách phục hồi được thiết kế rõ, trạng thái và tài nguyên vẫn ở tình trạng hợp lệ, tác dụng phụ được kiểm soát và đầu ra phản ánh trung thực kết quả.

## 19. Tài liệu tham khảo

- [Java 17 — `RuntimeException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/RuntimeException.html): nhóm ngoại lệ unchecked thường cần phân loại theo hợp đồng.
- [Java 17 — `IllegalStateException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalStateException.html): ngoại lệ biểu diễn trạng thái không cho phép thao tác.
- [Java 17 — `Throwable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): stack trace, cause, suppressed exceptions và cơ chế ném/bắt.
- [Java 17 — `CompletableFuture`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): trạng thái hoàn tất bất thường, `exceptionally`, `handle`, `join`.
- [Java 17 — `Objects.requireNonNull`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T)): xác nhận hợp đồng đối tượng không null.

**Ghi nhớ:** một `catch` không chứng minh có thể phục hồi. Khi gặp lỗi do vi phạm giả định nội bộ, **đừng tiếp tục dùng trạng thái có thể đã sai hoặc báo thành công giả**. Hãy kiểm tra bất biến trước khi công bố thay đổi, dừng đúng đơn vị công việc, giữ lỗi gốc cho chẩn đoán và chỉ tiếp tục khi có chiến lược phục hồi được kiểm chứng.