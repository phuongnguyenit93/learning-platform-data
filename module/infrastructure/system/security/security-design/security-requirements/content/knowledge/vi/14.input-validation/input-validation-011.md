# File name validation — Đặc tả kiểm tra tên tệp an toàn

## 1. Tên tệp là dữ liệu đầu vào, không phải quyền chọn nơi lưu

Một chức năng upload nhận tên `invoice.pdf` rồi ghép trực tiếp vào thư mục lưu trữ. Cách làm này có vẻ thuận tiện vì người vận hành nhìn thấy tên quen thuộc. Tuy nhiên, caller đang được tác động tới tên đối tượng mà server sẽ tạo, thay thế hoặc tìm kiếm.

Nếu đầu vào là một đường dẫn, tên có ý nghĩa đặc biệt trên hệ điều hành hoặc tên bị các thành phần diễn giải khác nhau, kết quả không còn đơn thuần là “lưu một tài liệu”. Hệ thống có thể ghi ngoài vùng dự kiến, ghi đè một tệp khác, chọn nhầm đối tượng hoặc tạo nội dung hiển thị gây hiểu nhầm.

Trong chương Input validation, **file name validation** là việc xác định và thực thi hợp đồng cho giá trị được gọi là tên tệp: được lấy từ đâu, mang ý nghĩa gì, được phép có dạng nào và được sử dụng ở những ranh giới nào.

Mục tiêu của bài là chuyển yêu cầu chung “kiểm tra tên tệp” thành các điều kiện có thể nghiệm thu. Thiết kế cần chứng minh:

- Người dùng không chọn được đường dẫn lưu trữ bằng cách đặt tên tệp.
- Tên hợp lệ được xử lý nhất quán qua parser, ứng dụng, kho lưu và luồng tải xuống.
- Đầu vào không hợp lệ bị từ chối rõ ràng, không được sửa ngầm thành một đối tượng khác.
- Tên tệp không thay thế kiểm tra nội dung, phân quyền hoặc bảo vệ đường dẫn.

Các ngưỡng và mã yêu cầu trong bài là ví dụ cho một hệ thống giả định, không phải một quy tắc đặt tên áp dụng cho mọi sản phẩm.

## 2. Phân biệt bốn giá trị thường bị gọi chung là “filename”

| Giá trị | Ai quyết định | Vai trò | Có được dùng trực tiếp làm đường dẫn không? |
|---|---|---|---|
| Tên do client gửi | Client hoặc nguồn tích hợp | Metadata chưa tin cậy | Không |
| Tên hiển thị đã qua chính sách | Ứng dụng theo hợp đồng sản phẩm | Hiển thị và gợi ý tên tải xuống | Không |
| ID bản ghi tệp | Server | Tra cứu metadata và kiểm tra quyền | Không được coi bản thân ID là quyền truy cập |
| Storage key hoặc tên vật lý | Server theo cấu trúc nội bộ | Xác định đối tượng trong vùng lưu được phép | Chỉ qua lớp lưu trữ được kiểm soát |

Ví dụ:

```text
client filename:     invoice-2026.pdf
display filename:    invoice-2026.pdf
file record ID:      file-demo-472
storage key:         9414d94f-4654-48c8-95fa-6e85edcc0bd0.blob
owner:               tenant-demo-12
state:               QUARANTINED
```

Trong ví dụ, storage key không được tạo bằng cách nối tên client vào một prefix. Tên hiển thị có thể thay đổi theo chức năng đổi tên, còn đối tượng lưu trữ vẫn được tra cứu bằng bản ghi và khóa nội bộ.

Nếu hai người upload cùng tên `invoice-2026.pdf`, hệ thống không cần ghi đè hoặc tự thêm hậu tố vào cùng một đường dẫn. Hai bản ghi có thể có hai storage key độc lập. Việc có cho phép trùng tên hiển thị trong cùng thư mục nghiệp vụ hay không là một quy tắc sản phẩm riêng.

OWASP khuyến nghị dùng tên do ứng dụng sinh, hạn chế tên do người dùng kiểm soát và đặt giới hạn phù hợp cho tên tệp. Bài học dùng nguyên tắc này làm cơ sở cho thiết kế phân tách metadata với khóa lưu trữ. Xem [OWASP File Upload Cheat Sheet — Filename Safety](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html#filename-safety).

## 3. Những cách tên tệp có thể vượt khỏi ý nghĩa metadata

### 3.1. Tên chứa cấu trúc đường dẫn

Các giá trị sau cần được xem là tình huống kiểm thử, không phải tên tệp phẳng thông thường:

```text
../report.pdf
folder/report.pdf
folder\report.pdf
/var/example/report.pdf
C:\example\report.pdf
C:report.pdf
\\server\share\report.pdf
```

Một số chuỗi mang ý nghĩa đường dẫn tương đối, tuyệt đối, theo ổ đĩa hoặc theo namespace của nền tảng. Cách diễn giải phụ thuộc hệ điều hành và API. Vì vậy, kiểm tra bằng parser đường dẫn của máy Linux không tự động bảo đảm an toàn khi dữ liệu sau đó được xử lý bởi một worker Windows.

Nếu hợp đồng chỉ nhận một tên phẳng, việc phát hiện dấu phân cách không phải là lý do để lấy phần cuối rồi tiếp tục. Một endpoint nghiêm ngặt có thể từ chối toàn bộ giá trị vì caller đã gửi sai hợp đồng.

Một số giao thức hoặc nguồn tích hợp thực sự gửi kèm đường dẫn. Khi cần hỗ trợ, lớp chuyển đổi phải được thiết kế riêng, xác định rõ cách lấy metadata và vẫn không dùng đường dẫn từ client làm nơi lưu.

### 3.2. Tên đặc biệt theo nền tảng

Windows có các tên thiết bị dành riêng như `CON`, `NUL`, `COM1` hoặc `LPT1`; việc thêm phần mở rộng không luôn làm chúng trở thành tên thông thường. Dấu chấm hoặc dấu cách ở cuối cũng có các hạn chế tương thích. Chính sách phải đối chiếu nền tảng thực tế, không chỉ kiểm tra một vài ví dụ. Xem [Microsoft — Naming Files, Paths, and Namespaces](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file).

Dấu hai chấm còn có ý nghĩa trong cách đặt tên stream của NTFS. Vì vậy, `report.pdf:extra` không nên được coi là một tên phẳng bình thường trong một chính sách cần tương thích với Windows. Tham khảo [Microsoft — File Streams](https://learn.microsoft.com/en-us/windows/win32/fileio/file-streams).

Không nên suy ra rằng mọi dấu hai chấm đều tạo cùng một tác động trên mọi nền tảng. Điều cần đặc tả là tập tên được ứng dụng chấp nhận và môi trường mà dữ liệu sẽ đi qua.

### 3.3. Tên gây nhầm lẫn về loại tệp

`report.pdf.exe`, `report.PDF`, `report.pdf.` hoặc tên có ký tự trông giống dấu chấm có thể được các lớp xử lý khác nhau. UI có thể rút gọn tên; một thành phần kiểm tra phần đầu hoặc phần mở rộng khác với thành phần phục vụ nội dung.

Yêu cầu phải xác định rõ cách nhận diện extension, có chấp nhận nhiều dấu chấm hay không và có phân biệt hoa thường hay không. Không dùng phép tìm chuỗi như “tên chứa .pdf” để kết luận tệp thuộc loại được phép.

Ngay cả tên đúng `report.pdf` cũng không chứng minh nội dung là PDF an toàn. Phần tên chỉ là một điều kiện metadata; các kiểm tra nội dung và cách phục vụ tệp thuộc những yêu cầu khác.

### 3.4. Tên đi vào những ngữ cảnh mới

Tên tệp có thể được hiển thị trong HTML, đưa vào log, thêm vào HTTP header, gửi vào email hoặc chuyển làm đối số cho công cụ xử lý. Một tên không làm thoát đường dẫn vẫn có thể chứa ký tự điều khiển hoặc dữ liệu nguy hiểm cho các ngữ cảnh này.

Do đó, “đã validate filename” không có nghĩa có thể chèn nguyên tên vào mọi đầu ra. Mỗi nơi sử dụng cần một API và cách biểu diễn phù hợp.

## 4. Kiến trúc ưu tiên: tên hiển thị tách khỏi storage key

Một luồng minh họa:

```text
Multipart / API input
        |
        v
Parser giao thức có giới hạn
        |
        v
Tên client chưa tin cậy
        |
        v
Chính sách tên hiển thị
        |
        +------> Metadata của bản ghi tệp
        |
        v
Server sinh storage key độc lập
        |
        v
Tạo đối tượng mới trong vùng quarantine riêng
        |
        v
Kiểm tra nội dung và quy trình upload liên quan
        |
        v
Công bố trạng thái READY theo điều kiện của hệ thống
```

Có ba ranh giới quan trọng.

Thứ nhất, parser giao thức chỉ giải mã và phân tích theo trách nhiệm của giao thức. Ứng dụng không tiếp tục giải mã lặp cho tới khi chuỗi “trông hợp lệ”. Đầu vào sau parse phải có một ý nghĩa thống nhất khi được kiểm tra và sử dụng.

Thứ hai, tên hiển thị là metadata. Một thao tác đổi tên không được tự động trở thành thao tác đổi đường dẫn vật lý hay di chuyển đối tượng giữa tenant.

Thứ ba, tên vật lý do server sinh không phụ thuộc vào khả năng tên gốc “trông an toàn”. Validation tên gốc vẫn cần cho trải nghiệm và các nơi sử dụng metadata, nhưng lỗi trong phần hiển thị không nên trao quyền chọn nơi ghi.

Một UUID hoặc ID khó đoán không thay thế kiểm tra quyền. Luồng đọc, tải xuống, đổi tên và xóa vẫn phải kiểm tra caller được phép thao tác với đúng bản ghi tệp.

## 5. Viết hợp đồng tên tệp rõ ràng

Một chính sách cần trả lời các nhóm câu hỏi sau.

### 5.1. Nguồn và giải mã

- Nhận tên từ tham số nào của giao thức hoặc field nào của API?
- Khi có nhiều nguồn tên, nguồn nào có ưu tiên và trường hợp mâu thuẫn xử lý ra sao?
- Parser có giới hạn độ dài header, số part và tổng metadata hay không?
- Dữ liệu nào đã được giao thức giải mã, dữ liệu nào chỉ là ký tự thông thường?

Không mặc định áp dụng URL decoding cho tên trong multipart. Chuỗi có dấu phần trăm chỉ được diễn giải theo quy tắc của trường dữ liệu và giao thức tương ứng. Nếu một tầng khác còn giải mã sau validation, thiết kế phải loại bỏ bất nhất đó.

### 5.2. Dạng tên và độ dài

Phải nêu rõ có nhận tên Unicode, khoảng trắng, nhiều dấu chấm, tên ẩn hoặc tên bắt đầu bằng dấu gạch ngang hay không. Những lựa chọn này phụ thuộc sản phẩm và các thành phần sử dụng tên.

Độ dài phải có đơn vị: byte UTF-8, code point hoặc đơn vị khác đã xác định. Với một chính sách chỉ nhận ASCII, byte UTF-8 và số ký tự ASCII trùng nhau; không được suy điều đó sang một chính sách Unicode.

Ngoài trần nghiệp vụ của tên, parser vẫn cần một trần trước khi tạo đối tượng chuỗi lớn. Không đọc metadata không giới hạn rồi mới kiểm tra tên dài.

### 5.3. Biến đổi cho phép

Nếu chuẩn hóa Unicode, trim hoặc chuẩn hóa hoa thường được cho phép, hợp đồng phải nói rõ thứ tự và giá trị nào được lưu. Không “sanitize” bằng cách xóa ký tự nguy hiểm rồi âm thầm chấp nhận kết quả.

Ví dụ `folder/report.pdf` bị sửa thành `folderreport.pdf` là thay đổi ý nghĩa, không phải chứng minh đầu vào ban đầu hợp lệ. Hai đầu vào khác nhau cũng có thể trở thành cùng một tên sau biến đổi.

Nếu sản phẩm muốn đề xuất một tên thay thế, có thể phản hồi tên đề xuất để người dùng xác nhận trong luồng sản phẩm. Nó phải là hành vi công khai, không phải cơ chế validation vô hình.

### 5.4. Chính sách extension

Đặc tả cần nêu extension được phép, cách tách extension và xử lý chữ hoa/chữ thường. Nếu chỉ hỗ trợ một dấu chấm giữa stem và extension thì phải nói rõ; đây là lựa chọn chặt cho một chức năng cụ thể, không phải định nghĩa chung của tên tệp hợp lệ.

Không dùng extension do client gửi để chọn một chương trình thực thi, quyết định MIME cuối cùng hoặc bỏ qua kiểm tra nội dung.

## 6. Hợp đồng minh họa cho endpoint nhận chứng từ

Giả sử một endpoint chỉ cần nhận tên chứng từ đơn giản, phục vụ một quy trình có mẫu đặt tên cố định. Đội sản phẩm quyết định dùng chính sách hẹp sau:

| Thuộc tính | Chính sách minh họa |
|---|---|
| Kiểu đầu vào | Chuỗi tên tệp sau parser giao thức |
| Missing, null, empty | Từ chối |
| Bộ ký tự | ASCII: chữ, số, gạch ngang, gạch dưới và một dấu chấm theo cấu trúc |
| Stem | 1 đến 64 ký tự; ký tự đầu là chữ hoặc số |
| Ký tự còn lại của stem | Chữ, số, `-`, `_` |
| Extension | Chính xác `pdf` hoặc `png`, chữ thường |
| Số dấu chấm | Một dấu chấm phân cách stem và extension |
| Tổng độ dài | Tối đa 68 ký tự ASCII, bao gồm dấu chấm và extension |
| Chuẩn hóa ngầm | Không trim, không đổi hoa thường, không giải mã thêm |
| Tên thiết bị dành riêng | Từ chối theo tập được khai báo trong chính sách |
| Tên hiển thị | Chính tên đã được chấp nhận |
| Storage key | Server sinh độc lập, không chứa tên client |
| Trùng tên hiển thị | Không tự ghi đè đối tượng; quy tắc trùng tên nghiệp vụ được xử lý riêng |

Chính sách này không hỗ trợ tên tiếng Việt có dấu hoặc tên có khoảng trắng. Đó là một đánh đổi rõ ràng của ví dụ, không phải khuyến nghị cấm tên quốc tế trong mọi ứng dụng.

Nếu sản phẩm cần giữ tên như `Hóa đơn tháng 11.pdf`, phải xây dựng một chính sách Unicode phù hợp cho metadata, giới hạn độ dài và bảo vệ các nơi hiển thị. Storage key vẫn nên độc lập với tên này.

## 7. Bộ yêu cầu bảo mật và bằng chứng

Các mã dưới đây là ví dụ để liên kết với rủi ro, thiết kế và kịch bản nghiệm thu của hệ thống.

### FNAME-01 — Tên client không chọn được đích lưu

Mọi thao tác tạo, đọc hoặc xóa đối tượng lưu phải dựa trên khóa nội bộ được tra cứu qua bản ghi đã kiểm tra quyền. Tên client và tên hiển thị không được ghép trực tiếp thành đường dẫn hoặc object key cho thao tác đó.

**Bằng chứng:** luồng ánh xạ bản ghi tới storage key; kiểm thử hai tên khác nhau, tên chứa đường dẫn và đổi tên metadata không làm thay đổi đích vật lý ngoài ý muốn.

### FNAME-02 — Chỉ chấp nhận tên theo hợp đồng đã công bố

Server phải thực thi giới hạn kiểu, độ dài, cấu trúc, bộ ký tự, extension và tên đặc biệt theo chính sách endpoint. Frontend không phải nơi duy nhất thực thi.

**Bằng chứng:** test vector hợp lệ và không hợp lệ; gọi API trực tiếp; kết quả thống nhất ở các đường upload, import và cập nhật metadata liên quan.

### FNAME-03 — Kiểm tra và sử dụng cùng biểu diễn

Tên phải được kiểm tra sau bước parse hoặc giải mã mà hợp đồng quy định. Không có lớp downstream tiếp tục biến đổi tên theo cách làm thay đổi ý nghĩa đã kiểm tra.

**Bằng chứng:** test tên có encoding, dấu phần trăm, Unicode và các nguồn metadata mâu thuẫn; ghi nhận giá trị thực sự đi tới từng thành phần.

### FNAME-04 — Không sửa ngầm tên không hợp lệ

Đầu vào sai hợp đồng phải bị từ chối hoặc được xử lý bằng luồng đổi tên được sản phẩm định nghĩa rõ. Không xóa ký tự, cắt độ dài hoặc tự lấy basename để làm đầu vào sai trở thành thành công mà caller không biết.

**Bằng chứng:** tên chứa path hoặc vượt biên không tạo một tên khác trong kho; response không báo upload thành công cho một đối tượng bị đổi nghĩa âm thầm.

### FNAME-05 — Không ghi đè khi va chạm khóa

Tạo đối tượng phải có ngữ nghĩa tạo mới có điều kiện, thất bại nếu khóa đã tồn tại. Không dùng kiểm tra tồn tại rồi ghi đè như hai thao tác độc lập.

**Bằng chứng:** kiểm thử cưỡng bức va chạm và tạo đồng thời; đối tượng hiện có giữ nguyên; retry nếu có phải dùng khóa mới theo ngân sách rõ ràng.

### FNAME-06 — Giới hạn đường dẫn và quyền hệ thống tệp

Nếu dùng filesystem, vùng lưu và các thư mục cha liên quan phải được cấu hình tin cậy, phân quyền phù hợp và không cho caller thay đổi cấu trúc đường dẫn. Biện pháp kiểm tra đường dẫn phải phù hợp với nguy cơ symlink và thay đổi đồng thời.

**Bằng chứng:** cấu hình quyền, deployment layout, kiểm thử đường dẫn thoát vùng và kịch bản symlink trong môi trường kiểm thử có kiểm soát.

### FNAME-07 — Tên không chứng minh an toàn nội dung

Kết quả validation tên chỉ xác nhận metadata đạt hợp đồng. Tệp không được chuyển sang trạng thái sẵn sàng sử dụng chỉ vì tên có extension được phép.

**Bằng chứng:** file có tên hợp lệ nhưng nội dung sai vẫn đi qua cơ chế kiểm tra nội dung và không được công bố trước khi đạt các điều kiện liên quan.

### FNAME-08 — Bảo vệ tên ở mọi ngữ cảnh đầu ra

Hiển thị tên, ghi log và tạo tên tải xuống phải dùng cơ chế phù hợp với ngữ cảnh; không nối nguyên metadata chưa tin cậy vào HTML, HTTP header hoặc lệnh shell.

**Bằng chứng:** kiểm thử ký tự điều khiển và tên quốc tế trên luồng được hỗ trợ; response/header/log không bị chèn bản ghi hay thay đổi cấu trúc.

### FNAME-09 — Tên không mở rộng quyền truy cập

Trùng tên, tên giống tài liệu hệ thống hoặc một ID đoán được không được cho phép truy cập tệp của người khác. Đổi tên và tải xuống phải kiểm tra quyền trên bản ghi trước khi truy cập đối tượng.

**Bằng chứng:** test chéo tenant, đổi tên thành tên tệp của người khác và truy cập trực tiếp bằng ID hoặc key ngoài quyền.

## 8. Ví dụ Java: validator tên phẳng và storage key độc lập

Đoạn mã sau minh họa đúng chính sách ASCII hẹp ở phần 6. Nó không phải bộ nhận diện loại nội dung và không phải toàn bộ dịch vụ upload.

```java
import java.io.IOException;
import java.nio.channels.SeekableByteChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class DocumentFileNames {
    private static final int MAX_NAME_LENGTH = 68;

    private static final Pattern NAME = Pattern.compile(
            "([A-Za-z0-9][A-Za-z0-9_-]{0,63})[.](pdf|png)");

    private static final Set<String> RESERVED = Set.of(
            "CON", "PRN", "AUX", "NUL");

    public static final class AcceptedName {
        private final String displayName;
        private final String storageKey;

        private AcceptedName(String displayName, String storageKey) {
            this.displayName = displayName;
            this.storageKey = storageKey;
        }

        public String displayName() {
            return displayName;
        }

        public String storageKey() {
            return storageKey;
        }
    }

    public static AcceptedName validateAndAllocateKey(String suppliedName) {
        if (suppliedName == null || suppliedName.isEmpty()) {
            throw failure("FILE_NAME_REQUIRED");
        }

        if (suppliedName.length() > MAX_NAME_LENGTH) {
            throw failure("FILE_NAME_TOO_LONG");
        }

        Matcher matcher = NAME.matcher(suppliedName);
        if (!matcher.matches()) {
            throw failure("FILE_NAME_INVALID_FORMAT");
        }

        String stem = matcher.group(1).toUpperCase(Locale.ROOT);
        if (isReserved(stem)) {
            throw failure("FILE_NAME_RESERVED");
        }

        // Không lấy storage key từ tên, extension hoặc đường dẫn client.
        String key = UUID.randomUUID() + ".blob";
        return new AcceptedName(suppliedName, key);
    }

    public static SeekableByteChannel openNewQuarantineObject(
            Path trustedPrivateRoot,
            AcceptedName acceptedName) throws IOException {

        Objects.requireNonNull(trustedPrivateRoot);
        Objects.requireNonNull(acceptedName);

        // Root là cấu hình tin cậy và được bảo vệ bằng quyền triển khai.
        Path root = trustedPrivateRoot.toRealPath();
        Path target = root.resolve(acceptedName.storageKey());

        return Files.newByteChannel(
                target,
                StandardOpenOption.WRITE,
                StandardOpenOption.CREATE_NEW);
    }

    private static boolean isReserved(String stem) {
        return RESERVED.contains(stem)
                || stem.matches("COM[1-9]")
                || stem.matches("LPT[1-9]");
    }

    private static IllegalArgumentException failure(String code) {
        return new IllegalArgumentException(code);
    }
}
```

Các đặc điểm cần đọc đúng:

- `matches()` kiểm tra toàn chuỗi, không tìm một đoạn tên có vẻ hợp lệ.
- Pattern chỉ nhận ASCII nên cách đo code unit ở đây không gây bất nhất Unicode trong tập tên được chấp nhận.
- Chính sách từ chối tên nhiều dấu chấm, separator, dấu hai chấm, khoảng trắng và ký tự điều khiển ngay ở cấu trúc.
- Các tên thiết bị ASCII trong chính sách được kiểm tra không phân biệt hoa thường; dạng Unicode khác không vượt qua pattern ASCII.
- `AcceptedName` có constructor riêng; caller không thể dùng public constructor để đưa storage key tùy ý vào phương thức lưu.
- Khóa lưu trữ dùng hậu tố trung tính `.blob`; không quyết định MIME hoặc trạng thái an toàn dựa trên extension client.
- Việc mở đối tượng trả về một channel để caller ghi qua chính handle đó, thay vì kiểm tra rồi đóng và mở lại theo tên.

Theo [Java Files API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html), tùy chọn `CREATE_NEW` tạo mới và thất bại nếu tên đã tồn tại; kiểm tra tồn tại cùng thao tác tạo được thực hiện nguyên tử theo cam kết của API. Cách này khác với `exists()` rồi ghi bằng chế độ có thể thay thế đối tượng.

Ví dụ giả định root cùng các thư mục cha được bảo vệ và caller không có khả năng tráo đổi chúng. `toRealPath()` trước khi mở không tự giải quyết mọi race nếu một tiến trình không tin cậy có quyền thay cấu trúc thư mục giữa hai thời điểm. Khi mô hình đe dọa có khả năng đó, cần cơ chế thao tác theo directory handle hoặc giải pháp cách ly phù hợp với nền tảng.

Caller vẫn phải đóng channel, giới hạn số byte thực tế ghi, xử lý tệp dở và chỉ công bố bản ghi sau khi hoàn tất các kiểm tra upload. Những trách nhiệm này không được suy ra là đã được đoạn validator tên thực hiện.

## 9. Khi phải xử lý đường dẫn: kiểm tra chuỗi là chưa đủ

Một số chức năng quản lý tệp thật sự cần nhận đường dẫn tương đối, chẳng hạn trình quản lý thư mục của người dùng. Đây là hợp đồng khác với một tên tệp phẳng.

Phải xác định root được phép, cấu trúc thành phần, quyền trên đối tượng và cách chống thoát vùng. Ví dụ sau chỉ minh họa kiểm tra đường dẫn ở mức từ vựng:

```java
Path candidate = root.resolve(relativePath).normalize();

if (!candidate.startsWith(root)) {
    throw new IllegalArgumentException("PATH_OUTSIDE_ROOT");
}
```

Không được sao chép đoạn này rồi coi là giải pháp đầy đủ. Nó giả định `root` và `candidate` cùng dạng biểu diễn phù hợp. `normalize()` xử lý các thành phần đường dẫn ở mức từ vựng, không kiểm chứng cấu trúc symlink thực tế. Một đường dẫn nhìn như nằm dưới root vẫn có thể dẫn tới nơi khác qua cấu trúc filesystem.

Cũng không thay `Path.startsWith` bằng so sánh prefix chuỗi. Một tên thư mục có cùng tiền tố văn bản không nhất thiết là thư mục con.

Đối với tệp chưa tồn tại, không thể chỉ gọi `toRealPath()` trên chính tệp rồi bỏ qua vấn đề tạo mới. Phải thiết kế cách truy cập thư mục cha, quyền sửa thư mục, thao tác tạo và xử lý race theo nền tảng. Xem [Java Path API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Path.html) và [OWASP Path Traversal Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Path_Traversal_Prevention_Cheat_Sheet.html).

Nếu nghiệp vụ không cần caller chọn đường dẫn, giải pháp đơn giản hơn về hợp đồng là không nhận đường dẫn ngay từ đầu. Cho caller gửi ID bản ghi và thực hiện phân quyền trên ID đó.

## 10. Unicode và tương thích nhiều nền tảng

Một hệ thống quốc tế có lý do chính đáng để giữ tên như `Báo cáo quý IV.pdf`. Không nên dùng một ví dụ allowlist ASCII làm lý do kết luận mọi tên khác ASCII đều nguy hiểm.

Thay vào đó, chính sách tên hiển thị cần giải quyết rõ:

- Độ dài theo đơn vị đã chọn và trần byte cho các kênh sẽ truyền tên.
- Dạng chuẩn hóa nếu sản phẩm muốn coi các biểu diễn Unicode tương đương là cùng một tên.
- Ký tự điều khiển, ký tự định hướng văn bản và những dạng có thể làm UI hiển thị gây hiểu nhầm.
- Quy tắc trùng tên theo hoa thường hoặc chuẩn hóa trong phạm vi nghiệp vụ.
- Cách hiển thị tên quá dài và extension mà không che mất thông tin quan trọng.
- Tập nền tảng mà tên được xuất ra hoặc đưa vào file archive.

Không nên hứa rằng normalization phát hiện mọi ký tự trông giống nhau. Một tên có ký tự giống chữ Latin có thể vẫn khác về biểu diễn; đó là vấn đề chính sách và trải nghiệm, không phải tác dụng tự động của NFC.

Khi xuất nhiều tệp vào một archive, tên metadata có thể một lần nữa trở thành đường dẫn entry. Cần có chính sách export riêng cho entry name, trùng tên và cấu trúc thư mục. Tên hiển thị đã được chấp nhận để lưu trong database không tự động là entry name an toàn.

Tương tự, tên entry nhận từ archive không phải một filename upload phẳng. Quy trình giải nén phải kiểm tra đường dẫn từng entry, kích thước và các đặc tính liên quan theo hợp đồng của chức năng đó.

## 11. Tên tải xuống và các ngữ cảnh đầu ra

### 11.1. HTTP header

Tên tải xuống thường xuất hiện trong `Content-Disposition`. Không tự nối chuỗi tên gốc vào một header. Cần dùng cơ chế tạo header phù hợp với framework, giới hạn ký tự điều khiển và hỗ trợ encoding tên quốc tế theo giao thức.

`filename` là thông tin gợi ý cho phía nhận, không phải quyền cho phía gửi áp đặt một đường dẫn cục bộ. RFC cũng cảnh báo về thành phần đường dẫn và sự tin cậy vào extension. Tham khảo [RFC 6266, mục 4.3](https://www.rfc-editor.org/rfc/rfc6266.html#section-4.3).

Tên tải xuống không được quyết định MIME một cách độc lập. Loại nội dung phục vụ phải gắn với dữ liệu và chính sách của hệ thống, kèm các kiểm soát tương ứng cho việc trình duyệt xử lý nội dung.

### 11.2. HTML và giao diện

Đưa tên vào text node bằng cơ chế escape của framework. Không tạo HTML bằng cách nối nguyên tên vào markup, thuộc tính hoặc script.

Với tên dài, UI có thể rút gọn phần hiển thị nhưng nên cho người dùng xem đầy đủ theo cách an toàn. Không để cách rút gọn che mất extension hoặc tạo ấn tượng sai về loại tệp.

### 11.3. Log và công cụ xử lý

Log nên dùng file record ID, mã chính sách và kết quả. Nếu cần tên, phải có giới hạn kích thước và biểu diễn an toàn, đồng thời cân nhắc tên có thể chứa dữ liệu cá nhân hoặc thông tin nghiệp vụ.

Không dùng tên gốc để ghép lệnh shell. Khi gọi công cụ xử lý, dùng API đối số có cấu trúc và đường dẫn nội bộ; vẫn phải hiểu quy tắc đối số của công cụ. Việc không qua shell không tự loại bỏ mọi trường hợp tên bị hiểu là tùy chọn.

## 12. Ma trận kiểm thử theo hợp đồng minh họa

Bảng sau áp dụng cho chính sách ASCII ở phần 6, không phải kết luận về tính hợp lệ của các tên trên mọi filesystem.

| Đầu vào hoặc kịch bản | Kết quả mong đợi | Điều được kiểm chứng |
|---|---|---|
| `invoice-2026.pdf` | Chấp nhận tên; chưa kết luận nội dung | Trường hợp nghiệp vụ thông thường |
| `scan_01.png` | Chấp nhận tên | Bộ ký tự và extension cho phép |
| Stem 64 ký tự + `.pdf` | Chấp nhận | Bao gồm biên 68 ký tự |
| Stem 65 ký tự + `.pdf` | Từ chối | Giới hạn stem và tổng tên |
| Missing, null, chuỗi rỗng | Từ chối | Hợp đồng bắt buộc có tên |
| `invoice.PDF` | Từ chối | Chính sách extension chữ thường, không đổi ngầm |
| `invoice.backup.pdf` | Từ chối | Hợp đồng chỉ một dấu chấm |
| `../invoice.pdf` | Từ chối | Không nhận đường dẫn tương đối |
| `folder\\invoice.pdf` | Từ chối | Không phụ thuộc separator của máy chạy test |
| Tên tuyệt đối, drive-relative hoặc UNC | Từ chối | Không cho chọn namespace lưu trữ |
| `NUL.pdf`, `con.png`, `COM1.pdf` | Từ chối | Tên đặc biệt trong chính sách |
| `invoice.pdf:extra` | Từ chối | Không nhận cấu trúc stream |
| Tên có dấu cách hoặc dấu chấm ở cuối | Từ chối | Không sửa ngầm để tương thích |
| Tên có CR, LF hoặc NUL | Từ chối | Không nhận ký tự điều khiển |
| Tên có dấu phần trăm hoặc Unicode | Từ chối trong ví dụ | Allowlist ASCII được thực thi rõ ràng |
| Hai upload cùng tên hiển thị | Không ghi đè | Storage key và metadata độc lập |
| Cưỡng bức trùng storage key | Tạo mới thất bại an toàn | Không thay thế đối tượng hiện có |
| Tên hợp lệ nhưng nội dung không phù hợp | Không công bố chỉ vì tên | Phân biệt metadata và kiểm tra nội dung |

Ngoài test hàm validator, cần thử payload thực sự qua parser giao thức. Nếu parser chỉ trả lại phần cuối của đường dẫn hoặc chọn một trong nhiều trường tên, phải biết hành vi đó có đúng hợp đồng hay không.

Với hệ thống hỗ trợ Unicode, thêm các test tương đương chuẩn hóa, tên có ký tự định hướng và tên trùng theo quy tắc sản phẩm. Không áp kỳ vọng từ bảng ASCII sang chính sách Unicode mà không điều chỉnh.

Khi kiểm thử khả năng containment hoặc symlink, thực hiện trong thư mục thử chuyên biệt với dữ liệu giả. Bằng chứng phải xác nhận không có đối tượng nào bị tạo hoặc thay đổi ngoài vùng được cấp cho kịch bản.

## 13. Tiêu chí chấp nhận ở mức hệ thống

Một bộ tiêu chí minh họa:

1. Mọi nguồn filename và phép biến đổi đã được xác định trong hợp đồng.
2. Server từ chối tên sai cấu trúc trước khi tạo tác động nghiệp vụ.
3. Storage key được sinh độc lập; không có tên client trong đường dẫn vật lý hoặc object key được tạo theo cách trực tiếp.
4. Các bản ghi trùng tên hiển thị không làm thay đổi tệp đã tồn tại.
5. Tạo mới có điều kiện và xử lý va chạm được xác minh trong kiểm thử đồng thời.
6. Vùng lưu, quyền thư mục và cơ chế containment phù hợp với mô hình đe dọa.
7. Download, đổi tên và xóa kiểm tra quyền trên đúng bản ghi.
8. Tên không phá cấu trúc HTML, header hoặc log ở các luồng được hỗ trợ.
9. Tệp chưa đạt điều kiện kiểm tra nội dung không được công bố chỉ vì filename hợp lệ.
10. Lỗi trả về không chứa đường dẫn nội bộ hoặc phản chiếu toàn bộ metadata không tin cậy.

Kết quả “validator PASS” chỉ chứng minh một phần hợp đồng. Để nghiệm thu ở mức hệ thống, cần cả cấu hình runtime, đường đi dữ liệu và trạng thái sau thao tác.

Đối với trường hợp thất bại sau khi đã tạo đối tượng quarantine, quy trình phải xác định cách quản lý tệp dở và metadata chưa hoàn tất. Cleanup cần dựa trên khóa nội bộ và trạng thái đáng tin, không lấy tên client làm mục tiêu xóa.

Nếu một đường xử lý cũ vẫn lưu trực tiếp theo tên client, đó là một khoảng trống cần ghi nhận. Không kết luận toàn bộ hệ thống đáp ứng chỉ vì endpoint mới đã dùng storage key.

## 14. Những đặc tả dễ dẫn tới triển khai sai

| Đặc tả chưa đủ | Vấn đề | Cách làm rõ |
|---|---|---|
| “Loại bỏ ../ trong tên” | Chỉ nhắm một mẫu, có thể sửa ngầm ý nghĩa | Định nghĩa tên phẳng hoặc đường dẫn riêng; từ chối sai hợp đồng |
| “Lấy basename là an toàn” | Hành vi phụ thuộc parser và nền tảng | Không dùng tên client chọn đích; quy định lớp chuyển đổi nếu cần |
| “Chỉ nhận .pdf” | Không rõ tách extension và không kiểm tra nội dung | Nêu grammar tên, extension và gate nội dung riêng |
| “Tên có UUID nên không cần ACL” | Tính khó đoán không phải quyền | Kiểm tra quyền trên bản ghi ở mọi thao tác |
| “Normalize rồi startsWith root” | Chưa xử lý cấu trúc filesystem và race | Đặt mô hình quyền, containment và thao tác tạo phù hợp |
| “Tên đã sanitize nên chèn vào header được” | Validation không thay thế biểu diễn đầu ra | Dùng API header và encoding theo giao thức |
| “Nếu trùng thì ghi đè” | Caller có thể thay đối tượng không được phép | Tạo mới có điều kiện; cập nhật tệp là chức năng có quyền riêng |
| “Mọi tên Unicode đều bị cấm” | Đánh đổi sản phẩm không được giải thích | Chính sách metadata quốc tế riêng, storage key độc lập |

## 15. Bài tập áp dụng

Một cổng nộp hồ sơ nhận filename từ multipart, lưu tệp bằng `uploadRoot + filename`, hiển thị filename trong danh sách và dùng lại nó làm tên tải xuống. Job tạo thumbnail chạy trên một hệ điều hành khác với API. Người dùng được đổi tên hồ sơ sau upload.

Hãy xây dựng yêu cầu có thể kiểm chứng:

1. Phân biệt tên client, tên hiển thị, ID bản ghi và storage key.
2. Chọn chính sách cho tên quốc tế và giải thích các phép biến đổi được phép.
3. Nêu cách bảo đảm đổi tên không làm di chuyển đối tượng hoặc mở rộng quyền.
4. Viết yêu cầu tạo mới không ghi đè và kịch bản va chạm khóa.
5. Xác định ranh giới kiểm tra đường dẫn, quyền thư mục và symlink.
6. Tạo ma trận test cho parser, Windows/Linux và luồng download.
7. Chỉ ra phần kiểm tra nội dung không được thay bằng extension.
8. Định nghĩa bằng chứng rằng một tên bị từ chối không tạo đối tượng công khai.

Kết quả cần nêu rõ chính sách, nơi thực thi và bằng chứng. Một regex hoặc một danh sách ký tự cấm chỉ là chi tiết triển khai, không đại diện cho toàn bộ yêu cầu bảo mật tên tệp.

## 16. Tài liệu tham khảo

- [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html): các lớp kiểm soát upload và tên do ứng dụng sinh.
- [OWASP Path Traversal Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Path_Traversal_Prevention_Cheat_Sheet.html): ranh giới đường dẫn và containment.
- [Microsoft — Naming Files, Paths, and Namespaces](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file): quy tắc và tên đặc biệt trên Windows.
- [Microsoft — File Streams](https://learn.microsoft.com/en-us/windows/win32/fileio/file-streams): ý nghĩa stream trong tên NTFS.
- [Java Path API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Path.html) và [Java Files API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): ngữ nghĩa thao tác đường dẫn và tạo tệp.
- [RFC 6266](https://www.rfc-editor.org/rfc/rfc6266.html): tên gợi ý trong Content-Disposition của HTTP.

Một thiết kế tên tệp có thể nghiệm thu phải kiểm soát cả ý nghĩa của tên lẫn nơi tên được sử dụng. Tách metadata khỏi khóa lưu trữ giúp thu hẹp quyền của dữ liệu đầu vào; hợp đồng rõ ràng và kiểm thử toàn luồng giúp chứng minh ranh giới đó được giữ khi hệ thống xử lý tệp thực tế.
