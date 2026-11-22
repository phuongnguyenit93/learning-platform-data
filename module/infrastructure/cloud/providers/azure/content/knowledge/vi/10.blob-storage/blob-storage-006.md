# Immutable storage, retention policy và legal hold

Doanh nghiệp thường lưu hóa đơn điện tử, chứng từ kế toán, hồ sơ giao dịch, bản ghi kiểm toán và dữ liệu phục vụ điều tra trong Azure Blob Storage. Những tệp này không chỉ cần được bảo vệ khỏi truy cập trái phép: tổ chức có thể phải chứng minh rằng nội dung **không bị chỉnh sửa hoặc xóa trước thời hạn bắt buộc**. Chẳng hạn, người dùng có quyền ghi dữ liệu không nên được phép thay hóa đơn đã phát hành bằng một bản có số tiền khác.

**Azure Blob Storage immutable storage** hỗ trợ mô hình **Write Once, Read Many (WORM)**: sau khi dữ liệu thuộc phạm vi bảo vệ, hệ thống có thể ngăn sửa hoặc xóa trong một khoảng thời gian quy định hoặc trong khi có **legal hold**. Để thiết kế an toàn, cần phân biệt thời hạn lưu giữ, khóa chính sách, phạm vi áp dụng ở container hay phiên bản blob, quyền vận hành và chi phí phát sinh.

Bài học thuộc chương **Lưu trữ đối tượng với Blob Storage** trong lộ trình khám phá Microsoft Azure: quản lý subscription và resource group, định danh Microsoft Entra ID, kết nối mạng ảo, dịch vụ tính toán, dữ liệu, giám sát, bảo vệ và kiểm soát chi phí cho kiến trúc ứng dụng.

> **Lưu ý về tuân thủ:** Ví dụ thời hạn lưu trong bài chỉ phục vụ học tập, không phải tư vấn pháp lý. Bộ phận pháp chế, quản trị hồ sơ và an ninh dữ liệu phải xác định luật áp dụng, loại hồ sơ, thời gian lưu và người có quyền thay đổi policy. Một tính năng WORM không tự làm tổ chức đạt một chứng nhận tuân thủ.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích WORM và sự khác biệt giữa **immutability**, **backup**, **soft delete** và **versioning**.
2. Phân biệt **time-based retention policy** với **legal hold** trong Azure Blob Storage.
3. Hiểu hai cách tổ chức bảo vệ: **container-level** và **version-level immutability**, gồm giới hạn tương thích.
4. Phân biệt policy **unlocked** để kiểm thử với **locked** khi đã được phê duyệt chính thức.
5. Thiết kế chu kỳ lưu trữ, hết hạn, đánh giá hồ sơ và quyền xóa sau khi hết nghĩa vụ.
6. Nhận diện tương tác giữa WORM với upload, append, lifecycle management và vận hành dữ liệu.
7. Thực hiện quy trình thiết kế/kiểm tra trên Azure portal và dùng Azure CLI để quan sát trạng thái.
8. Xử lý các lỗi như không thể overwrite, không thể delete, legal hold chưa được gỡ hoặc chi phí lưu trữ tăng.

## 1. Vì sao dữ liệu cần bất biến?

Ví dụ một hệ thống bán hàng lưu bản PDF của hóa đơn sau khi phát hành. Tệp được tạo một lần, sau đó có thể được đọc bởi kế toán, kiểm toán hoặc khách hàng. Rủi ro không chỉ là mất file do xóa nhầm, mà còn là việc một người có quyền ghi thay nội dung rồi phủ nhận sự thay đổi.

Với WORM, mục tiêu là:

- **Write once:** nội dung được chốt theo chính sách, không cho thao tác sửa hoặc xóa bị cấm trong thời gian bảo vệ.
- **Read many:** người có quyền vẫn đọc dữ liệu để phục vụ nghiệp vụ, kiểm toán hoặc pháp lý.
- **Retention:** dữ liệu được giữ đến khi đáp ứng thời hạn áp dụng; không thể tự ý rút ngắn thời gian đã khóa.
- **Legal hold:** một yêu cầu lưu giữ đặc biệt có thể ngăn xóa mà không cần biết trước ngày kết thúc.
- **Auditability:** tổ chức có thể theo dõi việc tạo, khóa, kéo dài hoặc gỡ chính sách theo quyền và tính năng ghi log hỗ trợ.

**Bất biến không đồng nghĩa bất khả xâm phạm.** Nếu danh tính đọc dữ liệu bị lộ, người tấn công có thể vẫn tải xuống tệp; nếu dữ liệu gốc sai ngay lúc ghi, WORM sẽ giữ bản sai ấy. Do đó cần kết hợp kiểm soát trước khi ghi, Microsoft Entra ID, RBAC, network firewall, mã hóa, giám sát và quy trình nghiệp vụ.

### Các tình huống sử dụng

| Tình huống | Nhu cầu | Cách tiếp cận |
|---|---|---|
| Hóa đơn hoặc chứng từ đã phát hành | Không được sửa/xóa trong số năm do chính sách xác định | Time-based retention, chọn phạm vi theo cách phát hành |
| Bản ghi kiểm toán | Tệp ghi log phải được giữ nguyên trong thời gian tối thiểu | WORM, thiết kế append/rotation phù hợp |
| Hồ sơ phục vụ tranh chấp | Không biết trước ngày kết thúc điều tra | Legal hold theo quyết định có thẩm quyền |
| Báo cáo tài chính định kỳ | Khóa bản chính thức nhưng vẫn lưu bản nháp có thể chỉnh | Tách vùng làm việc và vùng WORM |
| Dữ liệu được yêu cầu giữ lâu hơn thông thường | Không được tự động xóa khi hết thời hạn cũ | Xem xét kéo dài retention hoặc legal hold, có phê duyệt |

## 2. Bốn cơ chế dễ bị nhầm lẫn

**Immutable storage**, **retention**, **soft delete** và **versioning** đều liên quan đến dữ liệu trong Blob Storage nhưng có mục tiêu khác nhau.

| Cơ chế | Bảo vệ chính | Có ngăn sửa/xóa trong thời hạn bắt buộc? |
|---|---|---|
| **Time-based immutable retention** | Bảo vệ nội dung trong khoảng thời gian lưu giữ áp dụng | Có, theo loại policy và phạm vi được hỗ trợ |
| **Legal hold** | Giữ dữ liệu khi có yêu cầu lưu giữ pháp lý/nghiệp vụ chưa xác định ngày kết thúc | Có, trong khi hold còn hiệu lực theo phạm vi áp dụng |
| **Blob soft delete** | Cho phép phục hồi dữ liệu bị xóa trong khoảng thời gian cấu hình | Không phải thay thế cho WORM |
| **Blob versioning** | Giữ các phiên bản trước của blob khi có thao tác tạo/sửa phù hợp | Tự versioning không ngăn được quyền xóa các phiên bản nếu không có lớp bảo vệ thêm |
| **Backup / replication** | Hỗ trợ phục hồi sau lỗi hoặc mất dữ liệu | Không tự áp đặt nghĩa vụ lưu giữ bất biến |
| **Lifecycle management** | Chuyển tier hoặc xóa dữ liệu theo quy tắc quản trị vòng đời | Không được dùng để vượt qua immutability/hold còn hiệu lực |

Ví dụ, bật **versioning** giúp có thể tìm lại phiên bản cũ của một tệp; nhưng nếu người có quyền vẫn xóa được các phiên bản, nó không đáp ứng yêu cầu giữ dữ liệu không thể xóa. Với **version-level immutability**, mỗi phiên bản có thể được bảo vệ theo chính sách của nó, kết hợp điểm mạnh của versioning và WORM.

**Backup không thay thế WORM:** bản sao có thể là giải pháp khôi phục, còn WORM bảo vệ một đối tượng/phiên bản khỏi thay đổi được quy định. Nhiều tổ chức cần **cả hai**, vì tính bất biến không tự cung cấp tính sẵn sàng ứng dụng hoặc quy trình khôi phục vùng Azure bị sự cố.

## 3. Hai loại chính sách: time-based retention và legal hold

### 3.1. Time-based retention policy

**Time-based retention** đặt một khoảng thời gian mà dữ liệu thuộc phạm vi chính sách phải được giữ lại. Trong giai đoạn còn hiệu lực, các thao tác ghi đè/xóa bị cấm theo mô hình immutability đang sử dụng. Khi khoảng thời gian đã kết thúc, dữ liệu **không tự động được xóa** chỉ vì policy hết hạn; muốn giải phóng dung lượng phải có hành động/xử lý vòng đời được phép.

Ví dụ:

~~~text
Ngày 01/01/2027: tạo phiên bản hóa đơn chính thức
Retention policy: 365 ngày (giả định để học)
Trong thời gian bảo vệ:
  - Đọc: được phép nếu danh tính có quyền
  - Ghi đè/xóa bản được bảo vệ: bị từ chối
Sau thời hạn:
  - Có thể trở thành đối tượng đủ điều kiện xóa theo policy và quyền
  - Không có nghĩa Azure tự xóa ngay lúc hết hạn
~~~

Lưu ý mốc tính retention phụ thuộc loại policy, thời điểm tạo/chỉnh dữ liệu và hành vi của dịch vụ. Không nên tự tính ngày có thể xóa trên một giả định duy nhất; hãy xem trạng thái và thời hạn thực tế mà Azure hiển thị cho đối tượng/phiên bản.

### 3.2. Legal hold

**Legal hold** là trạng thái giữ dữ liệu để đáp ứng yêu cầu như tranh chấp, điều tra hoặc lệnh lưu giữ chứng cứ. Khác time-based retention, legal hold không cần xác định trước số ngày lưu giữ. Việc gỡ hold phải do người có thẩm quyền và theo quy trình được kiểm soát.

~~~text
Hồ sơ tranh chấp được đánh dấu legal hold
          |
          v
Không xóa/ghi đè dữ liệu thuộc phạm vi được bảo vệ
          |
          v
Quy trình pháp lý kết thúc?
    | Không -> tiếp tục hold
    | Có
    v
Phê duyệt gỡ legal hold theo chính sách tổ chức
          |
          v
Kiểm tra retention policy khác vẫn còn hiệu lực không
          |
          v
Chỉ xóa khi mọi hạn chế liên quan đã được giải quyết
~~~

Trong cách quản lý legal hold ở cấp container, Azure có thể sử dụng **hold tags** để phân biệt các yêu cầu giữ dữ liệu; việc thêm hoặc gỡ tag phải theo khả năng của API và quyền được cấp. **Gỡ một legal hold không tự bỏ qua time-based retention** còn đang hiệu lực.

### 3.3. Khi hai chính sách cùng bảo vệ dữ liệu

Một blob hoặc phiên bản có thể chịu các ràng buộc từ nhiều cơ chế theo phạm vi và khả năng hỗ trợ. Quy tắc thực tế là **chỉ xóa khi không còn chính sách bất biến nào chặn thao tác**.

| Time-based retention | Legal hold | Có thể xóa đối tượng đang được bảo vệ? |
|---|---|---|
| Chưa hết hạn | Không có | Không |
| Đã hết hạn | Còn hiệu lực | Không |
| Chưa hết hạn | Còn hiệu lực | Không |
| Đã hết hạn | Đã được gỡ | Có thể, nếu không còn hạn chế khác và quyền cho phép |

Bảng nhằm giải thích nguyên tắc. Trạng thái thực còn phụ thuộc cấp container/version, loại Blob, chính sách khác, quyền, soft delete và hành vi được hỗ trợ của API.

## 4. Container-level immutability và version-level immutability

Azure Blob Storage có thể hỗ trợ thiết lập chính sách bất biến theo **container** hoặc theo **phiên bản blob**, với điều kiện hỗ trợ riêng. Chọn sai phạm vi sẽ ảnh hưởng cách ứng dụng ghi dữ liệu và thời điểm được phép thay đổi.

### Container-level immutability

Chính sách ở cấp **container** bảo vệ dữ liệu trong container theo phạm vi chính sách. Mô hình này thường phù hợp khi toàn bộ các tệp trong một container có cùng nghĩa vụ lưu giữ, chẳng hạn container **invoices-final-2027** chỉ nhận chứng từ đã phát hành.

~~~text
Storage Account: stcompliancedemo
  |
  +-- Container: invoices-final-2027
        |
        +-- invoice-001.pdf
        +-- invoice-002.pdf
        +-- invoice-003.pdf
        |
        +-- Time-based immutable retention policy
            (phạm vi container, theo tính năng được hỗ trợ)
~~~

Container-level policy dễ quản trị khi nhiều blob cùng yêu cầu bảo vệ; nhưng có thể hạn chế thao tác ghi đè/điều chỉnh nội dung trên cùng tên blob. Với workload cần cập nhật nhiều lần, phải kiểm tra sự phù hợp trước khi khóa policy.

### Version-level immutability

**Version-level immutability** cho phép bảo vệ những **phiên bản blob** theo chính sách tương ứng. Cơ chế này phù hợp khi một tài liệu có nhiều bản hợp lệ mà mỗi bản cần giữ lại, ví dụ v1, v2 và v3 của hợp đồng.

~~~text
Container: contracts
  |
  +-- agreement-42.pdf
        |
        +-- Version A (immutable: giữ theo chính sách)
        +-- Version B (immutable: giữ theo chính sách)
        +-- Version C (có chính sách theo trạng thái hiện tại)
~~~

Tùy cách cấu hình, việc tạo **phiên bản mới** có thể vẫn được cho phép trong khi các phiên bản cũ đang được bảo vệ. Điều này không có nghĩa phiên bản cũ được sửa lại. Đối với mỗi phiên bản, việc đặt retention/hold và các thao tác được phép cần được đối chiếu với tính năng hiện hành.

**Điều kiện quan trọng:** version-level immutability cần được bật/cấu hình theo yêu cầu của Storage Account hoặc container và tính năng hỗ trợ. Không mặc định một container cũ có thể chuyển đổi tùy ý sang cơ chế version-level trong mọi cấu hình.

### So sánh lựa chọn phạm vi

| Tiêu chí | Container-level | Version-level |
|---|---|---|
| Đơn vị chính sách | Container và dữ liệu thuộc phạm vi của nó | Phiên bản cụ thể của blob hoặc cơ chế default policy tương ứng |
| Quản lý | Dễ quản trị khi hồ sơ cùng thời hạn | Linh hoạt khi phiên bản có yêu cầu khác nhau |
| Thay đổi cùng tên blob | Có thể bị hạn chế đáng kể trong thời gian bảo vệ | Có thể tạo phiên bản mới trong mô hình được hỗ trợ, bản cũ vẫn được bảo vệ |
| Theo dõi | Kiểm tra policy container và blobs liên quan | Theo dõi từng versionId và trạng thái retention/hold |
| Rủi ro vận hành | Áp quá rộng, làm gián đoạn ứng dụng cần overwrite | Số lượng phiên bản và chi phí tăng, chính sách per-version phức tạp |

Không lựa chọn cơ chế chỉ dựa vào sự tiện lợi của portal. Hãy dựa vào hành vi ghi thực tế, loại blob, tính năng Storage Account, giới hạn hỗ trợ và nghĩa vụ pháp lý.

## 5. Policy unlocked và locked

Time-based retention ở những cấp cấu hình hỗ trợ thường có trạng thái **unlocked** và **locked**. Đây là ranh giới an toàn quan trọng khi chuyển từ thử nghiệm sang hệ thống tuân thủ.

### Unlocked: giai đoạn chuẩn bị và kiểm thử

Chính sách **unlocked** cho phép điều chỉnh hoặc loại bỏ trong phạm vi quyền và giới hạn của dịch vụ; thường được dùng khi đang kiểm thử retention và xác minh hành vi ứng dụng. Không được nhầm unlocked policy với cam kết WORM đã được khóa chính thức để đáp ứng yêu cầu tuân thủ nghiêm ngặt.

Ví dụ, trước khi lưu hóa đơn thật, nhóm có thể thử upload, overwrite, delete và lifecycle trên container thử nghiệm; sau đó kiểm tra ứng dụng có đang dùng những thao tác bị chính sách chặn hay không.

### Locked: bảo vệ chính sách khỏi bị giảm hiệu lực

Khi **lock** time-based retention policy, những giới hạn quan trọng được áp dụng. Với mô hình được hỗ trợ, không thể tùy ý rút ngắn hoặc xóa policy đã khóa; một số trường hợp có thể **kéo dài** thời gian bảo vệ theo quy tắc dịch vụ. Việc khóa có tính chất **khó hoặc không thể đảo ngược** trong thời hạn chính sách.

Vì vậy:

1. Người tạo cấu hình phải có quyền và phê duyệt phù hợp.
2. Cần có người độc lập rà soát thời hạn, scope, loại blob và các luồng ứng dụng.
3. Nên thử nghiệm trên tài nguyên không chứa dữ liệu quan trọng trước.
4. Chỉ khóa khi tổ chức chấp nhận hệ quả về chỉnh sửa, xóa, migration và chi phí.
5. Ghi lại thay đổi qua Activity Log và bằng chứng phê duyệt.

**Không khóa một retention policy nhiều năm trong bài lab**: nó có thể khiến bạn không xóa được container, giải phóng dữ liệu hoặc dọn resource group như mong muốn, đồng thời vẫn phải trả chi phí Storage liên quan.

### Kéo dài thời hạn không phải thu hồi bảo vệ

Nếu bộ phận pháp chế yêu cầu giữ lâu hơn, có thể phải kéo dài retention theo khả năng của loại policy. **Không suy ra rằng có thể rút lại phần thời hạn kéo dài sau đó.** Mọi thay đổi phải được xét duyệt như một quyết định bảo vệ dữ liệu có hệ quả tài chính và pháp lý.

## 6. Protected append writes và dữ liệu liên tục

Một số hệ thống ghi log theo kiểu **append**: chỉ thêm bản ghi, không sửa nội dung cũ. Với WORM, hành vi ghi mới cần được thiết kế cẩn thận để không tạo lỗ hổng cho việc sửa dữ liệu được bảo vệ.

Azure có những tùy chọn **protected append writes** trong các phạm vi hỗ trợ. Chúng có thể cho phép kiểu ghi nối tiếp hợp lệ mà vẫn giữ yêu cầu bất biến với nội dung đã ghi; tuy nhiên **không phải mọi loại blob, mọi thao tác append và mọi loại policy đều hỗ trợ như nhau**.

| Nhu cầu | Cách thiết kế nên đánh giá |
|---|---|
| Hóa đơn PDF đã phát hành | Tạo blob mới với tên bất biến, khóa lưu giữ sau bước xác minh |
| Log liên tục | Kiểm tra hỗ trợ protected append writes, kiểu blob và chính sách tương ứng |
| Đối tượng được cập nhật nhiều lần | Xem xét version-level immutability hoặc tách bản nháp/bản chính thức |
| Batch log theo ngày | Tạo blob riêng theo khoảng thời gian, chốt tệp rồi áp retention |

**Không bật protected append writes chỉ để “cho ứng dụng ghi được bằng mọi giá”.** Cần hiểu cụ thể API nào còn được phép, dữ liệu nào không được sửa và liệu kết quả có phù hợp nghĩa vụ tuân thủ.

### Tách vùng bản nháp và bản chính thức

Một kiến trúc thường hữu ích:

~~~text
Ứng dụng tạo hồ sơ
       |
       v
Container: drafts
  - Cho phép chỉnh sửa theo quyền
  - Có validation và review
       |
       v
Quy trình phê duyệt / ký / chốt hồ sơ
       |
       v
Container: final-records
  - Tên blob duy nhất
  - Dữ liệu immutable theo policy
  - Hạn chế xóa, ghi đè
       |
       v
Hệ thống tra cứu và kiểm toán (read-only)
~~~

Điều quan trọng là **đóng băng dữ liệu đã được kiểm tra và chấp thuận**, không khóa ngay bản nháp có thể còn lỗi. Nếu phải sửa một hồ sơ đã chốt, nghiệp vụ có thể cần tạo bản điều chỉnh hoặc phiên bản mới kèm tham chiếu thay vì xóa bản cũ.

## 7. Retention period được lựa chọn thế nào?

Thời hạn bảo vệ nên đến từ **data classification** và **records retention schedule** của tổ chức, không dựa trên một con số chọn ngẫu nhiên.

### Ví dụ phân loại

| Nhóm dữ liệu | Retention minh họa | Đơn vị phê duyệt | Cần xem xét |
|---|---|---|---|
| Hóa đơn tài chính | Theo nghĩa vụ lưu trữ áp dụng | Pháp chế + tài chính | Mốc phát hành, điều chỉnh và tranh chấp |
| Chứng từ giao dịch | Theo hợp đồng/quy định liên quan | Quản lý hồ sơ + pháp chế | Khả năng cần giữ thêm khi có tranh chấp |
| Audit log | Theo chính sách an ninh và tuân thủ | An ninh thông tin | Tính toàn vẹn, truy vấn, luân chuyển |
| Hồ sơ điều tra | Đến khi được phép gỡ legal hold | Pháp chế hoặc điều tra | Người phê duyệt, chain of custody |
| Tệp thử nghiệm | Thời hạn ngắn và có kiểm soát | Chủ sở hữu lab | Không dùng locked policy kéo dài vô ích |

Các thời hạn trong bảng là **định hướng thiết kế**, không có con số pháp lý chung cho mọi quốc gia, ngành hoặc loại hồ sơ.

### Mốc tính thời hạn có ý nghĩa gì?

Một hồ sơ có thể có ngày upload, ngày phát hành, ngày chốt và ngày bắt đầu nghĩa vụ lưu. Những mốc này không nhất thiết trùng nhau. Thiết kế phải xác định:

- Sự kiện nghiệp vụ nào đánh dấu hồ sơ chính thức?
- Dữ liệu/phiên bản nào phải được giữ nguyên?
- Retention bắt đầu theo cơ chế dịch vụ tại thời điểm nào?
- Khi hết thời hạn, có cần giữ thêm do legal hold hoặc điều tra không?
- Ai quyết định dữ liệu đủ điều kiện xóa và ai chịu trách nhiệm thực hiện?

Không dùng phép cộng “ngày phát hành + số năm” để suy đoán trạng thái Azure khi loại policy tính theo mốc khác. Luôn kiểm tra hiệu lực thực của đối tượng trong Azure.

## 8. Kết hợp retention với legal hold trong vòng đời hồ sơ

Ví dụ một công ty đặt time-based retention cho hồ sơ đã phát hành. Đến giữa thời hạn, một giao dịch phát sinh tranh chấp và bộ phận pháp chế yêu cầu giữ hồ sơ cho đến khi giải quyết xong.

~~~text
Hồ sơ được tạo và chốt
        |
        v
Time-based retention đã có hiệu lực
        |
        v
Xuất hiện yêu cầu điều tra/tranh chấp
        |
        v
Đặt legal hold cho đúng scope
        |
        v
Đến ngày hết retention thông thường
        |
        v
Legal hold còn hiệu lực --> không được xóa
        |
        v
Pháp chế phê duyệt gỡ hold
        |
        v
Kiểm tra mọi ràng buộc và quyền còn lại
        |
        v
Đưa vào quy trình xóa có kiểm soát nếu đủ điều kiện
~~~

**Đừng dùng thời gian retention cố định để tự động gỡ một legal hold.** Legal hold phải được xử lý bằng quy trình nghiệp vụ có người hoặc hệ thống được ủy quyền xác nhận khi nghĩa vụ giữ dữ liệu kết thúc.

### Gắn lý do và bằng chứng quyết định

Hệ thống quản trị hồ sơ nên ghi rõ:

- Mã hồ sơ hoặc case ID.
- Lý do, nguồn yêu cầu và phạm vi legal hold.
- Người phê duyệt và người vận hành.
- Thời điểm bắt đầu hold, những lần thay đổi.
- Bằng chứng phê duyệt gỡ hold.
- Liên kết tới đối tượng hoặc danh sách phiên bản được giữ.

Không đặt dữ liệu cá nhân hoặc nội dung vụ việc nhạy cảm trực tiếp vào tên tài nguyên/tag nếu người dùng không cần quyền đó có thể xem. Hãy dùng mã tham chiếu và hệ thống quản lý hồ sơ có quyền truy cập thích hợp.

## 9. Tương tác với Blob versioning, soft delete và lifecycle management

### Blob versioning

Nếu ứng dụng tạo phiên bản mới sau mỗi lần sửa, versioning có thể hỗ trợ theo dõi lịch sử. **Version-level immutability** cho phép bảo vệ từng phiên bản trong mô hình phù hợp. Mỗi phiên bản được giữ có thể tính vào dung lượng lưu trữ và số lượng đối tượng, nên cần ước tính chi phí.

Đừng cho rằng bật versioning rồi khóa một phiên bản đã tự khóa tất cả phiên bản tương lai. Cần xác định chính sách mặc định/inheritance và hành vi version-level thực tế của container, cùng thủ tục áp policy cho bản chính thức.

### Soft delete

Soft delete có thời hạn phục hồi sau xóa nhầm, nhưng không thay thế retention WORM. Một blob chịu immutable retention đang có hiệu lực có thể từ chối thao tác xóa ngay từ đầu, thay vì đi vào trạng thái xóa mềm thông thường.

Khi retention hết hạn và dữ liệu được phép xóa, soft delete hoặc phiên bản cũ có thể khiến dung lượng tiếp tục được giữ một thời gian; cần tính trong quy trình giải phóng dữ liệu và chi phí.

### Lifecycle management

Lifecycle rules có thể chuyển access tier hoặc xóa dữ liệu theo tuổi/điều kiện trong phạm vi tính năng hỗ trợ. **Không thể dùng một rule tự động để vượt qua locked retention hoặc legal hold còn hiệu lực.** Một thao tác delete bị chặn không phải lỗi cần “bỏ qua” bằng cách mở quyền rộng hơn.

Việc tiering, rehydration, chuyển archive, tạo bản sao hoặc đổi loại blob có các giới hạn khi đối tượng đang immutable. Kiểm tra tương thích theo loại blob, retention mode và tier trước khi sử dụng trong quy trình tuân thủ.

### Replication và backup

Object replication, geo-redundancy và backup có mục đích khác immutability. Không giả định policy/legal hold của bản gốc tự động chuyển sang bản sao theo cách đáp ứng yêu cầu pháp lý. Với dữ liệu cần sao chép sang account/region khác, cần kiểm tra tính năng hỗ trợ, chính sách ở **cả nguồn và đích**, metadata/phiên bản, thời gian sao chép và khả năng khôi phục.

## 10. Thiết kế kiến trúc lưu hồ sơ bất biến

Giả sử một hệ thống phát hành hóa đơn trên Azure:

- API chạy trên Azure App Service hoặc VM trong mạng riêng.
- Storage Account **strecordsprod** có container **drafts** và **final-invoices**.
- Blob được phân loại và kiểm tra trước khi ghi vào container chính thức.
- Microsoft Entra ID/managed identity quản lý quyền upload và quyền đọc.
- Storage firewall/Private Endpoint giới hạn đường truy cập.
- Time-based immutable retention bảo vệ bản chính thức.
- Legal hold được đặt cho hồ sơ thuộc tranh chấp theo quy trình pháp chế.
- Azure Monitor/Activity Log hỗ trợ audit và cảnh báo thay đổi.

~~~text
Người dùng / hệ thống phát hành
              |
              v
       API có xác thực
              |
              v
     drafts (có thể sửa)
              |
        Kiểm tra dữ liệu
        + phê duyệt/ký
              |
              v
      final-invoices (WORM)
       |              |
       |              +---- Time-based retention
       |              +---- Legal hold khi có tranh chấp
       |
       v
  Truy vấn/audit bằng danh tính read-only
              |
              v
     Giám sát, log và kiểm soát chi phí
~~~

### Vì sao không cho API ghi đè trực tiếp?

Nếu API có thể ghi đè tên blob cũ, hành vi ấy xung đột mục tiêu bất biến. Mô hình tốt hơn là:

1. Client gửi bản nháp để ứng dụng xác minh.
2. Sau khi phát hành, tạo **tên blob chính thức duy nhất**.
3. Ghi nội dung và metadata cần thiết qua quy trình đã phê duyệt.
4. Xác nhận tệp có thể đọc được, checksum/nội dung phù hợp và audit record tồn tại.
5. Đảm bảo retention/hold áp dụng đúng scope.
6. Không sửa nội dung đã chốt; khi có điều chỉnh, tạo chứng từ điều chỉnh hoặc phiên bản mới theo quy trình nghiệp vụ.

Như vậy, WORM phản ánh **điểm chốt hồ sơ** chứ không khóa mọi file tạm trong lúc người dùng đang điền biểu mẫu.

### Quyền truy cập

| Vai trò nghiệp vụ | Quyền mong muốn | Lưu ý |
|---|---|---|
| Uploader/API | Chỉ ghi vào phạm vi được phép trước khi chốt | Managed identity và RBAC tối thiểu |
| Hệ thống phát hành | Tạo bản chính thức trong phạm vi đã kiểm soát | Giới hạn thao tác overwrite/delete |
| Người đọc hồ sơ | Chỉ đọc nội dung được cấp | Storage Blob Data Reader khi phù hợp |
| Người quản trị retention | Quản lý policy theo quy trình và quyền hẹp nhất | Tách khỏi role vận hành ứng dụng |
| Pháp chế/điều tra | Yêu cầu và phê duyệt legal hold | Quy trình hai người, lưu bằng chứng |
| Kiểm toán viên | Xem cấu hình/log và đọc hồ sơ phù hợp | Không cần quyền gỡ hold hoặc khóa |

**Lưu ý:** Quyền kiểm soát policy, legal hold và dữ liệu phụ thuộc chính xác vào Azure RBAC/management API của chức năng đang dùng. Không suy đoán rằng role có chữ “Reader” có thể xem mọi nội dung dữ liệu, hoặc role quản lý Storage tự động đủ điều kiện gỡ chính sách đã khóa.

## 11. Quy trình cấu hình có kiểm soát trên Azure portal

Đây là quy trình minh họa, **không hướng dẫn khóa policy nhiều năm trên tài nguyên thử nghiệm**. Những tên menu trong portal có thể thay đổi theo SKU/tính năng.

### Bước 1: xác định phạm vi và điều kiện hỗ trợ

Trước tiên:

1. Kiểm tra tenant, subscription, resource group và Storage Account.
2. Xác nhận loại account, namespace, loại blob, versioning và tính năng immutable storage được hỗ trợ.
3. Quyết định **container-level** hay **version-level**.
4. Xác định thời hạn và nguồn phê duyệt.
5. Kiểm tra những ứng dụng đang overwrite, delete, append, tiering hay replicate blob.
6. Xác nhận quyền quản trị chính sách, bảo mật và kế hoạch rollback **trước khi khóa**.

Không nên tạo/cấu hình WORM trên container đang có dữ liệu quan trọng mà chưa kiểm kê toàn bộ tác vụ ghi/xóa của ứng dụng.

### Bước 2: tạo container thử nghiệm riêng

Chuẩn bị container **records-lab** trong Storage Account dành riêng cho lab. Upload vài blob mẫu, ví dụ **receipt-001.txt** và **receipt-002.txt**. Sử dụng dữ liệu giả, không phải chứng từ khách hàng.

Nếu muốn thử version-level, cần kiểm tra cấu hình tài khoản/container và quy trình bật tính năng tương ứng trước khi tạo bản thử. Việc chuyển đổi có thể có giới hạn và ảnh hưởng tới dữ liệu hiện tại.

### Bước 3: khai báo time-based retention (unlocked)

Trong trang container hoặc thông tin policy tương ứng, tìm mục **Access policy/Immutable blob storage/Immutability policy** theo giao diện đang sử dụng. Tạo một time-based retention policy với **thời hạn thử nghiệm hợp lệ và được chủ sở hữu phê duyệt**.

Để kiểm tra trước khi khóa:

- Xác minh policy được áp dụng đúng container/phiên bản.
- Thử đọc blob bằng danh tính có quyền.
- Thử một thao tác sửa/xóa có kiểm soát đối với **dữ liệu giả**, ghi lại kết quả.
- Xác định hành vi khi tạo blob hoặc phiên bản mới.
- Kiểm tra app/pipeline có đang phụ thuộc overwrite hoặc xóa trước hạn.

**Không bấm Lock chỉ để xem nút hoạt động.** Khi khóa, bạn có thể không thể thu hồi policy như một cấu hình lab thông thường.

### Bước 4: xem xét khóa policy trước khi production

Trong tổ chức có yêu cầu WORM chính thức, thực hiện:

1. Kiểm tra bản ghi phê duyệt của pháp chế/quản trị hồ sơ.
2. Ghi lại scope, retention period, ngày dự kiến hết hạn và ảnh hưởng tài chính.
3. Xác minh hệ thống sản xuất không cần thao tác bị cấm.
4. Yêu cầu người có quyền độc lập thực hiện hoặc phê duyệt thao tác lock.
5. Xác minh trạng thái locked trong Azure và ghi nhận audit evidence.

Đây là **thao tác có hệ quả lâu dài**, không nên làm trong thử nghiệm không kiểm soát hoặc khi chưa rõ nghĩa vụ giữ dữ liệu.

### Bước 5: legal hold theo yêu cầu có thẩm quyền

Khi có case pháp lý thực, xác định container/phiên bản cần bảo vệ, người yêu cầu và mã case ID. Áp legal hold bằng portal/API được hỗ trợ theo quyền. Xác nhận:

- Hold có hiệu lực đúng scope.
- Những tác vụ xóa/ghi đè bị cấm theo mong đợi.
- Có bản ghi người yêu cầu, thời gian, căn cứ, approver.
- Quy trình gỡ hold **không** chạy tự động theo lịch retention thông thường.

Với legal hold ở phạm vi container, xem cơ chế **hold tags** được cung cấp. Không tự thêm/xóa tag chỉ để làm sạch giao diện nếu không có phê duyệt.

### Bước 6: thử luồng nghiệp vụ

Trong lab, thực hiện các bước trên dữ liệu giả:

| Thao tác | Kỳ vọng cần xác minh |
|---|---|
| Đọc blob được bảo vệ | Thành công nếu danh tính có quyền đọc và mạng cho phép |
| Overwrite nội dung immutable | Bị từ chối trong phạm vi chính sách áp dụng |
| Delete blob/version còn retention | Bị từ chối theo cơ chế WORM |
| Delete trong lúc còn legal hold | Bị từ chối |
| Ghi blob mới | Tùy loại policy/scope và kiểu upload; kiểm tra theo kịch bản |
| Tạo phiên bản mới | Tùy version-level support và policy |
| Lifecycle delete | Không vượt qua retention/hold còn hiệu lực |

Ghi lại mã lỗi, request ID, trạng thái policy và thời gian quan sát. Các mã lỗi HTTP/API cụ thể phụ thuộc tác vụ và loại policy.

### Bước 7: bật giám sát, phân quyền và báo cáo

Cấu hình Activity Log alert khi có thay đổi cấu hình quan trọng, diagnostic settings và cơ chế giám sát data plane phù hợp. Gắn tag cho resource, phân chia quyền quản trị WORM và quyền ứng dụng, theo dõi retention nearing expiry và chi phí lưu trữ.

## 12. Azure CLI: kiểm tra read-only trước khi thay đổi

Ví dụ sử dụng Azure CLI để **đọc thông tin** từ Storage Account/container đã có. Cần quyền thích hợp với control plane và/hoặc data plane; những tên sau chỉ là placeholder học tập.

### Kiểm tra subscription và tài khoản

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"

az storage account show \
  --resource-group "rg-compliance-lab" \
  --name "stcompliancedemo" \
  --query "{name:name,kind:kind,location:location,isHnsEnabled:isHnsEnabled,allowBlobPublicAccess:allowBlobPublicAccess}" \
  --output json
~~~

### Xem container và chính sách

~~~bash
az storage container show \
  --account-name "stcompliancedemo" \
  --name "records-lab" \
  --auth-mode login \
  --output json
~~~

Đối với các nhóm lệnh **immutability-policy** và **legal-hold** trong phiên bản Azure CLI đang dùng, kiểm tra hướng dẫn:

~~~bash
az storage container immutability-policy -h
az storage container legal-hold -h
~~~

Những lệnh này **chỉ hiển thị help**, không thay đổi policy. Sau khi xác nhận phiên bản CLI, có thể sử dụng thao tác **show** thích hợp với quyền được cấp để xem retention period, trạng thái lock hoặc legal hold ở container:

~~~bash
az storage container immutability-policy show \
  --account-name "stcompliancedemo" \
  --container-name "records-lab" \
  --output json

az storage container legal-hold show \
  --account-name "stcompliancedemo" \
  --container-name "records-lab" \
  --output json
~~~

Các câu lệnh show ở trên minh họa thao tác kiểm tra **container scope**. Đối với **version-level immutability**, dùng các thao tác hỗ trợ ở cấp blob/version và đúng versionId; không lấy trạng thái container rồi kết luận tất cả phiên bản đều có cùng retention. Tên tham số/khả năng của lệnh có thể thay đổi theo CLI extension/API, nên cần kiểm tra help phiên bản đang cài.

### Kiểm tra các phiên bản blob

Trong mô hình có Blob versioning và quyền thích hợp, có thể liệt kê blob và các version theo tùy chọn CLI hỗ trợ:

~~~bash
az storage blob list \
  --account-name "stcompliancedemo" \
  --container-name "records-lab" \
  --auth-mode login \
  --include v \
  --output json
~~~

Đầu ra chỉ nên được dùng để đối chiếu tên/versionId và những trường metadata hỗ trợ. Không suy ra quyền xóa chỉ từ việc một version xuất hiện trong danh sách.

### Không chạy các lệnh lock/clear trong bài lab

Các thao tác như **lock retention policy**, **set/clear legal hold**, **delete container** hoặc **delete blob version** có tác động pháp lý và vận hành. Bài học chỉ sử dụng lệnh đọc. Khi triển khai thật, cần change request, phê duyệt, người thực hiện có quyền phù hợp và bằng chứng kiểm tra sau thay đổi.

## 13. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không thể overwrite blob | Blob/container/version đang nằm trong WORM scope | Kiểm tra loại immutability, thời hạn và phiên bản |
| Không thể xóa blob sau số ngày đã định | Legal hold vẫn còn, tính thời hạn khác dự kiến hoặc còn policy khác | Kiểm tra expiry thực, hold và những ràng buộc liên quan |
| Không thể giảm retention period | Policy đã locked hoặc có giới hạn thay đổi | Xem trạng thái policy; không tìm cách vượt khóa |
| Không thể xóa container/resource | Dữ liệu bên trong còn immutable hoặc có hold | Xác định đối tượng bị giữ; làm việc với owner pháp chế/quản trị |
| Pipeline ghi log bị lỗi | Append/write không phù hợp WORM | Xem loại blob, protected append writes và thiết kế rotation |
| Không thấy policy trên blob version | Chỉ bật một loại scope hoặc policy chưa được áp dụng đúng phiên bản | Kiểm tra version-level feature và versionId |
| Lifecycle rule không xóa file | Retention/hold đang chặn thao tác xóa | Đối chiếu lifecycle policy với WORM |
| Chi phí Storage tăng bất thường | Retention dài, nhiều version, soft delete và dữ liệu nhàn rỗi | Xem capacity, version count, access tier và chính sách lưu |
| Auditor đọc được metadata nhưng không đọc nội dung | Quyền control plane và data plane khác nhau, network firewall | Xem RBAC data plane và private network/DNS |
| API báo 403/409 khi xóa | Có thể do RBAC/SAS/Storage firewall hoặc trạng thái immutability | Xem mã lỗi Storage chi tiết, request ID, policy và quyền |

### Không xử lý lỗi bằng cách nới quyền tùy tiện

Nếu ứng dụng không thể xóa một blob, việc cấp **Storage Blob Data Owner** hoặc bật public network access thường **không giải quyết được** khi thao tác bị chặn bởi immutable policy. Ngược lại, nếu API nhận 403 vì thiếu quyền hoặc mạng, không nên kết luận chắc chắn do WORM.

Quy trình điều tra:

1. Xác nhận Storage Account, container, blob name và **versionId** (nếu có).
2. Thu thập API operation, timestamp, request ID và mã lỗi chi tiết.
3. Kiểm tra retention policy/lock state và legal hold ở đúng scope.
4. Kiểm tra phương thức xác thực, RBAC/SAS và network rules nếu lỗi không rõ.
5. Xác định thao tác có phù hợp lifecycle/ứng dụng và chính sách WORM không.
6. Chỉ thực hiện thay đổi sau khi owner phù hợp phê duyệt; không thử gỡ hold hoặc khóa không thể đảo ngược.

## 14. Bảo mật: WORM chỉ là một phần của kiến trúc

### Định danh và quyền

Sử dụng **Microsoft Entra ID**, managed identity và **Azure RBAC** để tách:

- Danh tính ghi hồ sơ vào vùng draft.
- Danh tính tạo/chốt bản chính thức.
- Người được đọc nội dung cho mục đích kiểm toán.
- Người có quyền xem/thiết lập retention.
- Người có quyền và trách nhiệm yêu cầu/gỡ legal hold.

Không dùng account key có quyền quá rộng cho mọi dịch vụ. Nếu vẫn phải dùng Shared Key/SAS, giới hạn phạm vi, thời hạn và chuyển sang Entra ID khi workload hỗ trợ. Quyền sửa WORM policy cần kiểm soát tương xứng với khả năng thay đổi nghĩa vụ lưu giữ.

### Mạng và mã hóa

Azure Storage có thể giới hạn truy cập qua **Storage firewall** và **Private Endpoint**, trong khi ứng dụng giao tiếp bằng HTTPS. Mã hóa dữ liệu lưu trữ được dịch vụ hỗ trợ; có thể đánh giá yêu cầu customer-managed key/Key Vault theo chính sách.

Immutable storage **không thay thế** private networking hoặc xác thực. Một blob không thể xóa vẫn có thể bị đọc bởi người có quyền quá rộng. Nếu cần hạn chế tiết lộ dữ liệu, phải bảo vệ quyền đọc và đường kết nối.

### Khả năng xóa theo yêu cầu bảo vệ dữ liệu

WORM có thể xung đột với nhu cầu xóa thông tin cá nhân theo chính sách riêng tư nếu tổ chức lưu nhầm hoặc giữ quá lâu. Do vậy:

1. Chỉ đưa dữ liệu thật sự có nghĩa vụ giữ vào vùng bất biến.
2. Xác định căn cứ pháp lý, thời hạn và phân loại dữ liệu trước khi khóa.
3. Tránh lưu dư thông tin nhạy cảm trong tên blob, metadata hoặc logs.
4. Có quy trình yêu cầu xem xét ngoại lệ và quyết định lưu giữ/xóa.
5. Không hứa có thể xóa ngay một bản ghi còn locked retention hoặc legal hold.

## 15. Giám sát và quản trị vòng đời

### Những sự kiện nên theo dõi

- Thao tác thay đổi hoặc khóa retention policy.
- Thao tác thêm/gỡ legal hold hoặc thay đổi hold tags.
- Thao tác xóa/overwrite bị từ chối.
- Sự tăng đột biến của số blob/version và dung lượng lưu.
- Lỗi pipeline chốt hồ sơ, lỗi upload và dữ liệu chưa được bảo vệ đúng thời điểm.
- Việc chuyển tier, lifecycle hoặc copy dữ liệu thất bại do policy.

Sử dụng **Azure Activity Log** cho các thao tác control plane phù hợp, **Azure Monitor/diagnostic settings** cho data plane và cơ chế log mà dịch vụ hỗ trợ. Tên event/metric và độ chi tiết tùy API, account, cấu hình collection và phạm vi truy cập.

### Các chỉ số quản trị nên có

| Chỉ số | Ý nghĩa |
|---|---|
| Tổng hồ sơ chốt | Bao nhiêu bản chính thức được lưu |
| Hồ sơ có WORM hợp lệ | Đối chiếu số bản cần bảo vệ và số bản thực sự có policy |
| Hồ sơ có legal hold | Theo dõi nghĩa vụ giữ đặc biệt |
| Hồ sơ gần hết retention | Chuẩn bị rà soát/xóa theo quy trình, không xóa mù |
| Số version và tổng byte lưu | Giám sát tăng trưởng và chi phí |
| Thay đổi policy ngoài lịch | Phát hiện thay đổi không được phê duyệt |
| Lỗi ghi/xóa do immutability | Phát hiện ứng dụng không tương thích |
| Chi phí theo Storage Account/container/tag | Phân bổ ngân sách và tối ưu |

Không mặc định tất cả các chỉ số trên đều là metric Azure Monitor tích hợp; một số cần được tính từ inventory, metadata, log và hệ thống quản lý hồ sơ của ứng dụng.

### Kế hoạch sau khi hết retention

Không phải tất cả dữ liệu hết retention đều được phép xóa ngay. Có thể còn:

- Legal hold chưa gỡ.
- Quy định lưu giữ bổ sung.
- Phiên bản hoặc bản sao có policy khác.
- Quy trình nghiệp vụ hoặc đánh giá chứng cứ chưa hoàn thành.

Thiết kế một **eligibility review** để kiểm tra hồ sơ đủ điều kiện xóa, yêu cầu phê duyệt và lưu bằng chứng. Sau khi đủ điều kiện, có thể sử dụng lifecycle rule hoặc công cụ xóa dữ liệu theo khả năng hỗ trợ, cùng kiểm chứng hậu kỳ.

## 16. Chi phí của dữ liệu bất biến

Chi phí Blob Storage phụ thuộc dung lượng, access tier, thao tác, replication, truyền dữ liệu và các tính năng liên quan. Immutable retention có thể **làm tăng chi phí gián tiếp hoặc trực tiếp** vì:

1. Không được xóa dữ liệu để giải phóng dung lượng trước hạn.
2. Version-level retention giữ nhiều phiên bản cùng lúc.
3. Legal hold có thể kéo dài thời gian lưu vượt retention ban đầu.
4. Soft delete/snapshot/versioning có thể làm dữ liệu phụ vẫn tồn tại.
5. Object replication, backup hoặc lưu nhiều region tạo thêm bản sao/chi phí.
6. Monitoring, inventory và lưu log có phí theo lựa chọn.

Ví dụ giả định để ước tính:

~~~text
100.000 hóa đơn/tháng
Kích thước trung bình: 500 KiB/hóa đơn
Dữ liệu mới mỗi tháng khoảng 48,8 GiB (không tính overhead)

Nếu không xóa trước hạn và mỗi tháng tạo tương tự:
  12 tháng x ~48,8 GiB = ~585,6 GiB dữ liệu gốc

Chưa gồm:
  - phiên bản/snapshot, soft delete
  - replication và overhead
  - phí thao tác/đọc/ghi/tier
  - log, backup và các dịch vụ bổ sung
~~~

Đây là phép tính dung lượng minh họa, **không phải báo giá Azure**. Khi thực hiện dự toán, xác nhận đơn vị GiB/GB, giá theo region/tier, phí truy xuất, thời gian lưu bắt buộc và yêu cầu phục hồi. Dùng Azure Pricing Calculator và **Azure Cost Management** để theo dõi thực tế.

### Vì sao không nên khóa “càng lâu càng tốt”?

Khóa thời hạn quá dài:

- Giữ dữ liệu sau khi không còn mục đích hợp lệ.
- Gây khó khăn khi có yêu cầu xóa theo nghĩa vụ khác.
- Tăng chi phí dung lượng, phiên bản và bản sao.
- Hạn chế tái cấu trúc dữ liệu hoặc xóa tài nguyên.

Mức retention phù hợp là mức **đủ đáp ứng nghĩa vụ**, được phê duyệt, có tài liệu căn cứ và được rà soát khi có thay đổi pháp lý/nghiệp vụ.

## 17. Bài tập tình huống: kho lưu hóa đơn và hồ sơ tranh chấp

Một doanh nghiệp thương mại điện tử dùng Azure Blob Storage để lưu hóa đơn:

- Hệ thống phát hành khoảng 100.000 hóa đơn PDF mỗi tháng.
- Hóa đơn có giai đoạn bản nháp và giai đoạn chốt.
- Chính sách của doanh nghiệp yêu cầu giữ **5 năm** cho bản đã phát hành *(con số giả định trong bài tập)*.
- Một số hóa đơn liên quan tới tranh chấp có thể phải giữ lâu hơn.
- API kế toán cần đọc dữ liệu, nhưng không được chỉnh sửa bản đã phát hành.
- Doanh nghiệp cần giới hạn chi phí và không muốn khóa dữ liệu lab không cần thiết.

### Nhiệm vụ thiết kế

1. Chọn cách tách **drafts** và **final-invoices**. Có cần container khác cho từng năm hoặc từng loại dữ liệu không?
2. Quyết định dùng **container-level** hay **version-level** immutability, nêu lý do.
3. Mô tả quá trình upload, validation, chốt, bảo vệ và kiểm thử không overwrite.
4. Viết quy trình phê duyệt trước khi đổi từ unlocked sang locked policy.
5. Mô tả cách tạo legal hold cho một case đang tranh chấp và điều kiện gỡ.
6. Giải thích xử lý trường hợp hết 5 năm nhưng legal hold vẫn còn.
7. Nêu cách dùng RBAC, managed identity, Storage firewall/Private Endpoint và logging.
8. Tính tăng trưởng dữ liệu cơ bản và các yếu tố làm chi phí lớn hơn dự toán.
9. Thiết kế cơ chế báo cáo hồ sơ gần hết hạn và quy trình xác định đủ điều kiện xóa.
10. Nêu ba bài kiểm thử tiêu cực cần thực hiện trước production.

### Gợi ý lời giải

Một phương án là dùng **drafts** cho dữ liệu có thể sửa, còn **final-invoices** dùng tên blob bất biến và chính sách time-based retention được phê duyệt. Nếu có nhu cầu tạo bản điều chỉnh, tạo blob/phiên bản mới thay vì sửa bản cũ; lựa chọn container-level hay version-level phải phụ thuộc yêu cầu cập nhật và hỗ trợ dịch vụ.

Khi có tranh chấp, áp legal hold đúng phạm vi và ghi case ID. Đến cuối năm thứ năm, nếu legal hold còn hiệu lực thì hồ sơ **không được xóa**. Chỉ gỡ hold khi có quyết định phù hợp; việc hết retention thông thường không tự xóa hồ sơ và không tự gỡ hold.

## 18. Checklist trước khi áp dụng WORM trên production

| Nhóm | Điều phải xác minh |
|---|---|
| Pháp lý | Loại hồ sơ, nghĩa vụ lưu, thời hạn và người phê duyệt |
| Scope | Container-level hay version-level, account/feature tương thích |
| Dữ liệu | Đã phân biệt bản nháp và bản chính thức |
| Ứng dụng | Không còn overwrite/delete bị cấm sau khi chốt |
| Retention | Thời hạn, mốc tính, policy trạng thái phù hợp |
| Lock | Có review và phê duyệt độc lập trước thao tác khó đảo ngược |
| Legal hold | Có case ID, scope, owner và quy trình gỡ hold |
| Versioning | Hiểu hiệu lực từng phiên bản và chi phí đi kèm |
| Lifecycle | Rules không xung đột yêu cầu WORM |
| IAM | Role quản trị WORM tách khỏi quyền ứng dụng |
| Network | Firewall, private endpoint, HTTPS và DNS được kiểm tra |
| Audit | Activity Log, diagnostic settings, lưu bằng chứng thay đổi |
| Chi phí | Tính dung lượng, tier, bản sao, version/soft delete và log |
| Nghiệm thu | Thử read được phép, overwrite/delete bị chặn, legal hold đúng |
| Kết thúc | Có eligibility review và quy trình xóa sau khi đủ điều kiện |

## 19. Câu hỏi tự kiểm tra

1. WORM nghĩa là gì và giải quyết vấn đề nào khác với backup?
2. Vì sao một Storage Account có bật Blob versioning chưa chắc đạt yêu cầu immutable storage?
3. Time-based retention khác legal hold thế nào về ngày kết thúc và quy trình gỡ?
4. Một blob đã hết retention nhưng vẫn có legal hold thì có được xóa không?
5. Container-level và version-level immutability khác nhau ở phạm vi và hành vi cập nhật ra sao?
6. Vì sao không nên khóa retention policy trong môi trường lab trước khi kiểm thử?
7. Policy locked có thể tùy ý rút ngắn thời hạn không? Kéo dài retention có hệ quả gì?
8. Protected append writes phục vụ tình huống nào? Vì sao phải kiểm tra loại blob và thao tác hỗ trợ?
9. Vì sao cần tách container drafts và final-records?
10. Khi API báo không thể xóa một blob, cần kiểm tra những cơ chế và quyền nào?
11. Vì sao lifecycle management không thể tự xóa dữ liệu còn WORM/hold hiệu lực?
12. Retention hết hạn có khiến blob tự động bị xóa không?
13. Vì sao người có quyền read vẫn có thể làm lộ dữ liệu dù WORM đang bảo vệ nó?
14. Trong hệ thống hóa đơn có nhiều bản điều chỉnh, cần đánh giá version-level immutability thế nào?
15. Những thành phần nào khiến chi phí lưu trữ lâu dài cao hơn số byte dữ liệu gốc?
16. Vì sao phải kiểm thử cả backup/replication và chính sách WORM ở hệ thống đích?
17. Ai nên có quyền khóa policy và ai quyết định gỡ legal hold?

## Tài liệu tham khảo

- Microsoft Learn — *Immutable storage for Azure Blob Storage*: https://learn.microsoft.com/azure/storage/blobs/immutable-storage-overview
- Microsoft Learn — *Configure immutability policies for containers*: https://learn.microsoft.com/azure/storage/blobs/immutable-policy-configure-container-scope
- Microsoft Learn — *Configure immutability policies for blob versions*: https://learn.microsoft.com/azure/storage/blobs/immutable-policy-configure-version-scope
- Microsoft Learn — *Blob versioning*: https://learn.microsoft.com/azure/storage/blobs/versioning-overview
- Microsoft Learn — *Soft delete for blobs*: https://learn.microsoft.com/azure/storage/blobs/soft-delete-blob-overview
- Microsoft Learn — *Blob lifecycle management*: https://learn.microsoft.com/azure/storage/blobs/lifecycle-management-overview
- Microsoft Learn — *Authorize access to Azure Blob Storage*: https://learn.microsoft.com/azure/storage/blobs/authorize-access-azure-active-directory
- Microsoft Learn — *Azure Storage firewalls and virtual networks*: https://learn.microsoft.com/azure/storage/common/storage-network-security
