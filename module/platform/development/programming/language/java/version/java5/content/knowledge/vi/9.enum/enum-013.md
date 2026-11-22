# Định danh ổn định khi trao đổi dữ liệu thay cho phụ thuộc ordinal()

## 1. Thứ tự khai báo không phải mã nghiệp vụ

`ordinal()` trả về vị trí của hằng enum trong phần khai báo, bắt đầu từ 0. Một enum có thứ tự `WAITING, SENT, DELIVERED` sẽ cho `SENT.ordinal()` bằng 1.

Nếu hệ thống lưu số 1 vào cơ sở dữ liệu hoặc gửi số đó trong một thông điệp rồi bên nhận hiểu theo `values()[1]`, hai phía đang ngầm thống nhất về **thứ tự khai báo Java**, không phải một mã nghiệp vụ được thiết kế rõ ràng.

Khi thêm `PACKING` vào trước `SENT`, vị trí 1 nay là `PACKING`. Số đã được lưu vẫn hợp lệ về mặt phạm vi nhưng có thể bị hiểu thành một trạng thái khác mà không phát sinh ngoại lệ.

| Phiên bản minh họa | Thứ tự khai báo | Hằng ở vị trí 1 |
| --- | --- | --- |
| Trước khi thêm | `WAITING, SENT, DELIVERED` | `SENT` |
| Sau khi thêm | `WAITING, PACKING, SENT, DELIVERED` | `PACKING` |

Đây là lỗi hợp đồng dữ liệu: thay đổi thứ tự mã nguồn đã làm thay đổi nghĩa của dữ liệu cũ. Nguy hiểm không chỉ nằm ở việc nhận một số ngoài giới hạn, mà còn ở việc nhận số trong giới hạn nhưng giải mã sai nghĩa.

`ordinal()` không phải API bị loại bỏ; nó có ý nghĩa là vị trí hằng. Vấn đề là dùng vị trí đó làm định danh bền vững cho dữ liệu trao đổi hoặc dữ liệu lưu lâu dài.

Hợp đồng của phương thức được nêu tại [Enum.ordinal](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Enum.html#ordinal()).

## 2. Tách các loại thông tin của một hằng enum

| Thông tin | Ví dụ | Mức ổn định cần hiểu |
| --- | --- | --- |
| Vị trí khai báo | `ordinal() == 3` | Thay đổi khi thêm/xóa/sắp xếp lại hằng trước đó |
| Tên hằng Java | `SENT` từ `name()` | Không phụ thuộc vị trí, nhưng đổi tên hằng sẽ đổi chuỗi |
| Biểu diễn hiển thị | `Đã gửi` | Có thể đổi theo ngôn ngữ hoặc cách viết giao diện |
| Mã trao đổi tường minh | `sent` từ `code()` | Do hợp đồng ứng dụng quyết định và phải được giữ ổn định |

`name()` tốt hơn vị trí khi vấn đề chỉ là đổi thứ tự. Nhưng nếu tên hằng Java có thể được refactor, việc gửi tên ấy ra ngoài cũng tạo một ràng buộc tương thích cần quản lý.

Dùng `name()` làm mã không tự sai nếu hệ thống chủ đích công bố tên hằng là hợp đồng và cam kết không đổi tùy tiện. Mã tường minh hữu ích khi muốn tách quyền đổi tên trong Java khỏi định danh mà các hệ thống khác hoặc dữ liệu đã lưu đang sử dụng.

`toString()` mặc định có thể trả tên hằng, nhưng có thể được enum ghi đè để biểu diễn nội dung thân thiện hơn. Vì thế không lấy một nhãn hiển thị hay một `toString()` phục vụ log làm mã trao đổi mặc nhiên.

Đối chiếu [Enum.name](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Enum.html#name()) và [Enum.toString](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Enum.html#toString()).

## 3. Thiết kế mã tường minh

Ví dụ một hằng có mã công khai:

```java
SENT("sent")
```

Đây là phần khai báo một hằng trong enum, không phải câu lệnh độc lập. Mã `sent` có thể được giữ nguyên dù một phiên bản Java sau đổi tên hằng thành `DISPATCHED`, miễn ý nghĩa nghiệp vụ của nó vẫn tương ứng và bộ giải mã được cập nhật đúng.

Để một mã thật sự ổn định, cần có quy tắc:

- Mỗi ý nghĩa có một mã duy nhất trong phạm vi hợp đồng.
- Không phát sinh mã từ `ordinal()` hoặc từ vị trí trong một mảng cấu hình có thể đổi.
- Không tái sử dụng mã cũ cho một ý nghĩa mới sau khi bỏ một trạng thái.
- Quy định rõ chữ hoa/chữ thường, khoảng trắng và dạng ký tự được chấp nhận.
- Giữ mã tách khỏi nhãn hiển thị và bản dịch.
- Coi việc đổi mã đã công bố là thay đổi hợp đồng dữ liệu, không chỉ là refactor mã nguồn.

Mã không nhất thiết phải là chuỗi. Nếu một giao thức thật sự yêu cầu số, có thể dùng một trường mã số tường minh như 10, 20, 30, cùng ánh xạ được kiểm tra. Điểm quan trọng là mã được gán và quản lý theo hợp đồng, không lấy tự động từ vị trí hằng.

Giữ một trường `final` giúp ngăn thay đổi mã trên từng đối tượng enum, nhưng chưa đủ bảo đảm tương thích giữa các phiên bản. Một lập trình viên vẫn có thể sửa literal trong mã nguồn; cần có kiểm thử và quy trình thay đổi hợp đồng.

## 4. Ghi mã và đọc mã phải là hai bước rõ ràng

Khi gửi hoặc lưu, lấy mã bằng một API chuyên biệt như `state.code()`. Ví dụ dữ liệu JSON mong muốn:

```json
{
  "state": "sent"
}
```

Ví dụ JSON này minh họa hợp đồng dữ liệu, không ngụ ý một thư viện serialization sẽ tự dùng `code()` chỉ vì getter đó tồn tại.

Ở phía nhận, cần một phép tra cứu mã ngược về enum. `Enum.valueOf(ShipmentState.class, "SENT")` tìm theo **tên hằng Java**, không tự tìm trường `code` có giá trị `"sent"`.

Có thể dùng một bảng tra cứu được tạo sau khi các hằng enum đã được khởi tạo. Khi xây bảng, kiểm tra mã trống và mã trùng để tránh tình trạng hai hằng cùng chiếm một định danh.

Trong ví dụ dưới, bảng được tạo ở phần khởi tạo tĩnh sau danh sách hằng. Hàm tạo enum chỉ kiểm tra dữ liệu của hằng; nó không cố thêm từng hằng vào một bảng tĩnh chưa được khởi tạo hoàn chỉnh.

Chính sách giải mã được tách thành hai lựa chọn:

| API | Kết quả khi mã chưa biết | Mục đích |
| --- | --- | --- |
| `findByCode` | `Optional.empty()` | Để tầng gọi tự quyết định cách xử lý |
| `fromCode` | Ném `IllegalArgumentException` | Khi hợp đồng yêu cầu mã phải được hỗ trợ |

Hai API trong ví dụ so khớp chính xác và phân biệt hoa/thường. Không tự `trim` hoặc đổi chữ thường âm thầm. Nếu cần chấp nhận các dạng khác, hãy công bố quy tắc chuẩn hóa hoặc alias và kiểm tra xung đột rõ ràng.

## 5. Chương trình chạy đầy đủ

Lưu thành `StableEnumCodeDemo.java`. Hai enum đầu chỉ dùng để minh họa rủi ro của vị trí; `ShipmentState` là ví dụ dùng mã tường minh.

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

public class StableEnumCodeDemo {
    enum OriginalOrder {
        WAITING, SENT, DELIVERED
    }

    enum AfterInsert {
        WAITING, PACKING, SENT, DELIVERED
    }

    enum ShipmentState {
        DELIVERED("delivered"),
        WAITING("waiting"),
        PACKING("packing"),
        SENT("sent");

        private final String code;
        private static final Map<String, ShipmentState> BY_CODE = buildIndex();

        ShipmentState(String code) {
            this.code = Objects.requireNonNull(code, "code");
            if (code.isBlank()) {
                throw new IllegalArgumentException("Blank shipment state code");
            }
        }

        public String code() {
            return code;
        }

        private static Map<String, ShipmentState> buildIndex() {
            Map<String, ShipmentState> index = new HashMap<>();
            for (ShipmentState state : values()) {
                ShipmentState previous = index.put(state.code, state);
                if (previous != null) {
                    throw new IllegalStateException("Duplicate code: " + state.code);
                }
            }
            return Map.copyOf(index);
        }

        public static Optional<ShipmentState> findByCode(String code) {
            return code == null ? Optional.empty() : Optional.ofNullable(BY_CODE.get(code));
        }

        public static ShipmentState fromCode(String code) {
            return findByCode(code).orElseThrow(
                    () -> new IllegalArgumentException("Unknown shipment state code: " + code));
        }
    }

    public static void main(String[] args) {
        int storedPosition = OriginalOrder.SENT.ordinal();
        System.out.println("stored position=" + storedPosition);
        System.out.println("same position after insert="
                + AfterInsert.values()[storedPosition].name());

        ShipmentState state = ShipmentState.fromCode("sent");
        System.out.println("decoded name=" + state.name());
        System.out.println("encoded code=" + state.code());

        boolean roundTrip = true;
        for (ShipmentState value : ShipmentState.values()) {
            roundTrip &= ShipmentState.fromCode(value.code()) == value;
        }
        System.out.println("round trip=" + roundTrip);
        System.out.println("uppercase accepted="
                + ShipmentState.findByCode("SENT").isPresent());
        System.out.println("future code accepted="
                + ShipmentState.findByCode("returned").isPresent());
        System.out.println("null accepted="
                + ShipmentState.findByCode(null).isPresent());

        try {
            ShipmentState.fromCode("returned");
        } catch (IllegalArgumentException expected) {
            System.out.println("unknown code=rejected");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 -Xlint:all -Werror StableEnumCodeDemo.java
java StableEnumCodeDemo
```

Stdout:

```text
stored position=1
same position after insert=PACKING
decoded name=SENT
encoded code=sent
round trip=true
uppercase accepted=false
future code accepted=false
null accepted=false
unknown code=rejected
```

`ShipmentState` cố ý có thứ tự khai báo khác với thứ tự nghiệp vụ minh họa ban đầu. Mã `sent` vẫn giải mã thành `SENT` vì bảng tra cứu dựa vào trường mã, không dựa vào vị trí.

Phép kiểm tra round trip xác nhận rằng mỗi hằng được ghi thành mã rồi đọc lại trở về chính hằng đó. Tính duy nhất của bảng mã được kiểm tra khi khởi tạo enum; có mã trùng sẽ làm khởi tạo thất bại thay vì ghi đè âm thầm.

`findByCode(null)` được xử lý trước khi tra trong bảng bất biến, nên không dựa vào việc cấu trúc map có hỗ trợ khóa `null` hay không.

## 6. Mã chưa biết và tương thích giữa các phiên bản

Khi một phiên bản mới gửi `returned` nhưng phiên bản cũ chưa có trạng thái tương ứng, cần một quyết định tại biên hệ thống. Không tự đổi mọi mã chưa biết thành `WAITING`, vì như vậy dữ liệu không được hỗ trợ có thể bị diễn giải thành một trạng thái nghiệp vụ bình thường.

Các lựa chọn phụ thuộc hợp đồng:

- Từ chối đầu vào với lỗi rõ khi phía nhận bắt buộc hiểu trạng thái để xử lý đúng.
- Giữ nguyên chuỗi mã gốc trong một mô hình dữ liệu biên để chuyển tiếp hoặc hiển thị trạng thái chưa hỗ trợ, nếu đó là chức năng được thiết kế.
- Dùng một trạng thái `UNKNOWN` riêng chỉ khi có quy tắc rõ cho hành vi của nó; nếu cần chuyển tiếp chính xác, vẫn phải giữ mã gốc thay vì làm mất thông tin.

Thêm một hằng mới không có nghĩa mọi bên nhận cũ tự hiểu được nó. Mã ổn định giải quyết việc nhận diện nhất quán, không tự giải quyết mọi vấn đề phiên bản của giao thức.

Nếu đổi tên một mã đã công bố, có thể cần tạm chấp nhận mã cũ như alias đọc và chỉ ghi một mã chuẩn đã thống nhất. Alias phải ánh xạ tới cùng ý nghĩa, có giới hạn vòng đời rõ và không xung đột với mã đang dùng cho ý nghĩa khác.

Không dùng thứ tự `ordinal()` để suy ra quy trình trạng thái hợp lệ, quyền chuyển trạng thái hoặc mức ưu tiên xử lý. Những quan hệ nghiệp vụ ấy cần dữ liệu/hành vi được thiết kế riêng.

## 7. Áp dụng ở biên API, thông điệp và lưu trữ

Có trường `code` và `fromCode` chưa tự làm mọi lớp tích hợp dùng chúng. Cần kiểm tra đường dữ liệu thật:

1. Bộ ghi JSON hoặc thông điệp phải được cấu hình/gọi rõ để gửi mã theo hợp đồng.
2. Bộ đọc phải dùng ánh xạ mã đúng và có chính sách mã chưa biết.
3. Tầng lưu trữ phải ghi mã tường minh mong muốn, không vô tình dùng mapping theo vị trí.
4. Log, nhãn giao diện và bản dịch có thể dùng biểu diễn khác, nhưng không được âm thầm thay định danh trao đổi.
5. Kiểm thử phải đọc/ghi qua adapter thật của hệ thống, không chỉ gọi riêng `code()` trong một unit test.

Tùy thư viện, adapter có thể là converter, serializer/deserializer hoặc codec. Không có một quy tắc Java chung rằng khai báo enum có một getter mới sẽ tự thay đổi mọi thư viện.

Nếu dữ liệu đã được lưu theo vị trí, không chuyển mù quáng bằng `Enum.values()[oldNumber]` của phiên bản hiện tại. Cần xác minh enum và thứ tự thực tế tại thời điểm dữ liệu được tạo, có thể theo phiên bản schema hoặc đợt triển khai.

Một kế hoạch chuyển đổi cần ánh xạ cũ đã được kiểm chứng, cách xử lý giá trị không rõ, kiểm tra dữ liệu sau chuyển đổi và sự phối hợp giữa bên ghi/bên đọc. Nếu không có bằng chứng xác định nghĩa cũ của một con số, phải coi đó là dữ liệu chưa được giải nghĩa đầy đủ thay vì đoán.

## 8. Những kiểm tra giúp giữ hợp đồng ổn định

| Kiểm tra | Lỗi có thể phát hiện |
| --- | --- |
| Mã không rỗng và không trùng | Hai hằng chiếm cùng mã hoặc hằng chưa có mã |
| Round trip enum → mã → enum | Bộ ghi và bộ đọc không thống nhất |
| Bảng mã công khai cố định được kiểm chứng | Vô tình đổi mã literal khi refactor |
| Ca mã chưa biết, null, sai hoa/thường | Chính sách biên không rõ hoặc tự chuyển sai trạng thái |
| Dữ liệu mẫu từ phiên bản trước | Tương thích đọc dữ liệu đã phát hành |
| Đọc/ghi qua adapter thực tế | Framework vẫn dùng name/toString/ordinal trái với dự định |

Không xem một kiểm tra sinh mọi kỳ vọng từ chính trường `code` hiện tại là đủ bảo vệ hợp đồng cũ. Nếu cả mã và giá trị kỳ vọng đều đổi theo cùng nguồn hiện tại, kiểm tra có thể vẫn xanh dù định danh đã bị đổi so với phiên bản được phát hành.

Với mã quan trọng được bên khác sử dụng, cần một mốc kỳ vọng độc lập phù hợp như bảng mã giao thức được duyệt hoặc các dữ liệu tương thích đã công bố.

## 9. Tự kiểm tra

1. Vì sao lưu số `ordinal()` có thể sai nghĩa dù số vẫn nằm trong phạm vi enum mới?
2. `name()` có phụ thuộc thứ tự khai báo không? Nó có bất biến trước việc đổi tên hằng không?
3. Một getter `code()` có tự buộc mọi thư viện JSON dùng mã đó không?
4. Vì sao không nên mặc định mọi mã chưa biết thành trạng thái đầu tiên?
5. Nếu enum cần mã số thay vì chuỗi, có bắt buộc dùng ordinal không?

Đáp án:

1. Thêm hoặc sắp xếp hằng làm vị trí cũ chỉ tới một ý nghĩa khác mà không nhất thiết gây lỗi chỉ số.
2. Không phụ thuộc vị trí, nhưng đổi tên hằng sẽ đổi giá trị trả về của `name()`.
3. Không. Cần adapter/cấu hình ghi và đọc đúng, rồi kiểm thử đường dữ liệu thực tế.
4. Vì làm mất thông tin và có thể biến dữ liệu không được hỗ trợ thành một trạng thái nghiệp vụ sai.
5. Không. Dùng trường mã số tường minh và ánh xạ được quản lý như hợp đồng.

Hãy coi mã trao đổi là một định danh được công bố, tách khỏi vị trí enum, tên triển khai và nhãn hiển thị. Sự ổn định đến từ hợp đồng và kiểm tra tương thích, không tự đến từ việc dùng enum.
