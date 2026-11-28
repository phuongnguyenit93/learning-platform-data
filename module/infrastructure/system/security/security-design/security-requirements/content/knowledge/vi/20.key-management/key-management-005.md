# Key rotation

## 1. Mục tiêu và phạm vi

Key rotation là quá trình đưa key material mới vào sử dụng và điều chỉnh cách hệ thống sử dụng khóa cũ theo một chính sách đã xác định. Một lần rotation có thể tạo phiên bản mới trong cùng một tài nguyên khóa hoặc tạo tài nguyên khóa mới rồi chuyển các bên sử dụng sang nó.

Rotation không chỉ là tạo thêm một khóa. Hệ thống phải chuyển đúng các thao tác mới, giữ khả năng xử lý dữ liệu cũ còn cần thiết, kiểm soát cache và những thành phần chưa cập nhật, rồi kết thúc việc dùng khóa cũ ở thời điểm phù hợp.

Trong thiết kế yêu cầu bảo mật, câu “khóa được xoay định kỳ” chưa xác định đủ điều kiện hoàn thành. Cần biết đang xoay loại khóa nào, mục tiêu giảm rủi ro là gì, tác động tới dữ liệu hoặc chữ ký cũ ra sao và bằng chứng nào xác nhận toàn bộ quá trình.

Sau bài này, người học có thể:

- Phân biệt rotation với re-encryption, rewrap, disable và destruction.
- Đặc tả thời điểm ngừng dùng khóa cũ cho thao tác mới mà vẫn xử lý dữ liệu lịch sử theo policy.
- Thiết kế chuyển đổi cho khóa mã hóa dữ liệu, khóa bọc khóa và khóa ký.
- Xử lý cache, cạnh tranh, retry, backup và khả năng khôi phục.
- Viết tiêu chí nghiệm thu cho rotation thông thường và rotation khi nghi ngờ lộ khóa.

Bài dùng các phiên bản `v1`, `v2` để mô tả logic. API và trạng thái của từng KMS/HSM có thể khác mô hình này; không mặc định mọi sản phẩm đều cho người dùng truy cập hoặc quản lý từng phiên bản key material theo cùng một cách.

## 2. Những khái niệm phải phân biệt

### 2.1. Key identity khác key material

Key material là phần bí mật hoặc cặp giá trị mật mã thực sự được dùng. Key ID, alias và URI là cách hệ thống tham chiếu hoặc chọn khóa theo hợp đồng của nền tảng.

Đổi tên một khóa hoặc cập nhật một nhãn không tự tạo key material mới. Ngược lại, một nhà cung cấp có thể thay key material trong khi giữ nguyên định danh tài nguyên khóa.

Ví dụ, AWS KMS mô tả rotation key material trong cùng logical key và tự chọn material phù hợp khi giải mã ciphertext cũ. Vì vậy, không thể chỉ nhìn Key ID không đổi rồi kết luận không có rotation. [AWS KMS: Rotate keys](https://docs.aws.amazon.com/kms/latest/developerguide/rotate-keys.html)

### 2.2. Các thao tác có tác động khác nhau

| Thao tác | Điều thay đổi | Điều không nên tự suy ra |
| --- | --- | --- |
| Rotation | Key material/phiên bản hoặc khóa được chọn cho sử dụng tiếp theo | Dữ liệu cũ đã được mã hóa lại |
| Re-encryption | Dữ liệu được bảo vệ lại bằng khóa hoặc profile đích | Mọi bản sao lịch sử đã biến mất |
| Rewrap | Bản bọc của một DEK được thay sang KEK khác | Chính DEK hoặc nội dung được mã hóa bằng DEK đã thay đổi |
| Disable/restrict usage | Hệ thống không cho dùng khóa ở một số hoặc mọi thao tác | Key material đã bị xóa vĩnh viễn |
| Revocation | Thay đổi việc chấp nhận hoặc quyền dùng khóa theo policy | Mọi cache hoặc bên ngoài đã nhận thay đổi ngay lập tức |
| Destruction | Loại bỏ key material theo khả năng và quy trình của nền tảng | Không còn dữ liệu cần khóa đó để phục hồi |

Một kế hoạch có thể gồm nhiều thao tác, nhưng phải ghi rõ thứ tự và điều kiện. Không dùng từ “rotate” để che việc chỉ thay alias hoặc để ngầm bao gồm một bước xóa khóa chưa được kiểm chứng.

### 2.3. Thời gian tạo bảo vệ và thời gian xử lý dữ liệu cũ

NIST phân biệt thời gian khóa được dùng để áp dụng bảo vệ với thời gian khóa tương ứng được dùng để xử lý dữ liệu đã được bảo vệ. Hai khoảng có thể khác nhau, chẳng hạn ngừng ký bằng private key nhưng vẫn giữ khả năng kiểm tra chữ ký bằng public key. [NIST SP 800-57 Part 1 Rev. 5](https://nvlpubs.nist.gov/nistpubs/specialpublications/nist.sp.800-57pt1r5.pdf)

Trong ứng dụng mã hóa, điều này có thể được thể hiện thành policy: không dùng `v1` cho dữ liệu mới nữa, nhưng vẫn cho giải mã những bản ghi `v1` còn nằm trong thời gian lưu và trong phạm vi được phép.

Không coi mọi khóa đã hết thời gian tạo bảo vệ mới là khóa có thể xóa ngay.

## 3. Khi nào cần rotation và mục tiêu thực tế

### 3.1. Policy phải gắn với loại khóa và rủi ro

Các yếu tố cần xem xét gồm thuật toán/profile, số lần sử dụng, khối lượng dữ liệu, cách bảo vệ khóa, mức độ phân phối key material và hậu quả nếu một phiên bản bị lộ. NIST thảo luận cryptoperiod dựa trên rủi ro và điều kiện sử dụng, không chỉ một mốc lịch tùy ý. [NIST SP 800-57 Part 1 Rev. 5, mục 5.3](https://nvlpubs.nist.gov/nistpubs/specialpublications/nist.sp.800-57pt1r5.pdf)

Một policy có thể kích hoạt rotation theo thời gian, giới hạn số lần dùng khóa hoặc một sự kiện thay đổi mức tin cậy. Khi có nhiều giới hạn, cần quy định điều kiện nào đến trước sẽ kích hoạt việc chuyển đổi.

Một con số như “90 ngày” chỉ có ý nghĩa khi gắn với loại khóa, phạm vi và căn cứ cụ thể. Không lấy cùng một chu kỳ áp cho DEK, KEK, khóa ký và mọi loại secret rồi coi tất cả có cùng mức bảo vệ.

### 3.2. Rotation thông thường khác xử lý lộ khóa

Rotation thông thường có thể cho phép thời gian chồng lấp và tiếp tục đọc bằng khóa cũ. Khi nghi ngờ hoặc xác nhận lộ khóa, thời gian chồng lấp đó có thể không còn phù hợp.

Kế hoạch sự cố cần đánh giá ai có thể đã lấy key material, ciphertext, bản bọc DEK hoặc chữ ký liên quan; có cần ngừng ghi, hạn chế đọc, mã hóa lại hoặc thu hồi việc chấp nhận chữ ký không.

Không tự động áp kế hoạch chuyển đổi chậm theo lịch cho một khóa đã bị nghi ngờ chiếm quyền. Cũng không xóa khóa tức thì mà bỏ qua hậu quả mất dữ liệu cần giữ; hành động phải theo quyết định ứng phó có căn cứ.

### 3.3. Rotation không thu hồi một bản sao khóa đã bị lấy đi

Nếu một bên đã có khóa cũ và ciphertext cũ, đổi khóa đang dùng trong hệ thống không làm họ mất khả năng tính toán trên những bản sao đó.

Tương tự, mã hóa lại dữ liệu đang quản lý không xóa những bản sao dữ liệu hoặc khóa đã ở ngoài phạm vi kiểm soát. Yêu cầu cần nêu đúng mục tiêu: bảo vệ thao tác và dữ liệu tiếp theo, giảm phụ thuộc vào khóa cũ hoặc phục hồi ranh giới cho những dữ liệu còn được quản lý.

### 3.4. Chứng chỉ mới không nhất thiết là khóa mới

Gia hạn một chứng chỉ có thể vẫn dùng cùng cặp khóa. Nếu mục tiêu là thay key material, phải xác nhận cặp khóa thực sự được thay, không chỉ thời hạn chứng chỉ hoặc tên alias.

Nếu rotation đi cùng đổi thuật toán hoặc profile, cần kế hoạch tương thích riêng. Thay key material và thay cách diễn giải ciphertext là hai thay đổi khác nhau.

## 4. Mô hình trạng thái và thao tác được phép

### 4.1. Trạng thái minh họa cho khóa mã hóa

| Trạng thái logic | Mã hóa dữ liệu mới | Giải mã dữ liệu hiện hữu | Ý nghĩa |
| --- | --- | --- | --- |
| PREPARED | Chưa dùng cho dữ liệu sản phẩm | Chỉ kiểm chứng trong phạm vi chuẩn bị được phép | Khóa mới đã tạo nhưng chưa kích hoạt |
| ACTIVE_FOR_NEW | Được phép trong phạm vi quyền | Được phép trong phạm vi quyền | Phiên bản được chọn cho thao tác mới |
| DECRYPT_ONLY | Không | Được phép theo policy dữ liệu cũ | Đã kết thúc thời gian dùng cho bảo vệ mới |
| DISABLED | Không | Không trong luồng online này | Tạm ngừng hoặc chặn sử dụng |
| DESTROYED | Không | Không thể dựa vào material đã bị hủy | Bước kết thúc cần bằng chứng đủ trước đó |

Đây là mô hình policy ứng dụng, không phải tên trạng thái chuẩn chung của mọi KMS. Một sản phẩm có thể cần kết hợp trạng thái key, quyền API và logic dịch vụ để đạt cùng điều kiện.

Thông tin “compromised” nên được coi là một điều kiện rủi ro có thể làm thay đổi policy, không phải một trạng thái bình thường tự chuyển trở lại active chỉ vì job rotation đã chạy xong.

### 4.2. Chuỗi chuyển đổi thông thường

```text
Chuẩn bị v2 và kiểm chứng khả năng dùng
    → phân phối quyền/cấu hình cần thiết
    → chuyển thao tác mới sang v2
    → dừng v1 cho thao tác mới theo mốc hiệu lực
    → xử lý dữ liệu còn phụ thuộc v1 theo kế hoạch
    → kiểm chứng điều kiện ngừng sử dụng v1
    → disable hoặc destruction theo policy đã phê duyệt
```

Một thao tác đọc dữ liệu lịch sử có thể tiếp tục dùng `v1` trong khi dữ liệu mới dùng `v2`. Luồng đọc cần chọn đúng phiên bản theo thông tin đã được kiểm soát của dữ liệu, không thử giải mã bằng mọi khóa mà dịch vụ nhìn thấy.

### 4.3. Mốc hiệu lực phải đủ cụ thể

Giả sử hệ thống cho phép tối đa 120 giây truyền thay đổi cấu hình kể từ lúc kích hoạt `v2`. Đây là giá trị minh họa, không phải chuẩn chung.

Policy có thể yêu cầu: mọi thao tác mã hóa mới bắt đầu sau mốc kết thúc đó phải dùng `v2`. Cần định nghĩa riêng request đã bắt đầu, job đang chạy hoặc bản ghi chưa commit được xử lý thế nào.

Nếu mục tiêu mạnh hơn là “không có ciphertext `v1` nào được commit sau mốc”, chỉ kiểm tra khóa lúc bắt đầu request chưa đủ. Cần cơ chế thực thi tại thời điểm phù hợp hoặc drain các thao tác cũ theo thiết kế.

## 5. DEK, KEK, rewrap và dữ liệu hiện hữu

### 5.1. Hai tầng khóa của envelope encryption

```text
Nội dung ── được mã hóa bằng DEK ──> ciphertext

DEK ── được bọc bằng KEK phiên bản v1 ──> wrapped DEK v1
```

Khi xoay KEK sang `v2`, có thể cần bọc lại DEK để thu được wrapped DEK mới. Nội dung vẫn dùng cùng DEK nếu chỉ thực hiện rewrap.

Lịch rotation của KEK không tự thay cho giới hạn sử dụng của DEK. Nếu DEK cần thay vì đã dùng quá giới hạn hoặc có nguy cơ bị lộ, cần kế hoạch cho chính DEK và dữ liệu nó bảo vệ.

### 5.2. Không giả định KMS tự mã hóa lại mọi dữ liệu

AWS KMS nêu rõ rotation KMS key không xoay những data key đã được tạo và không tự mã hóa lại dữ liệu được bảo vệ. Thay đổi key material ở tầng KMS không tự xử lý một DEK đã bị lộ. [AWS KMS: Rotation và dữ liệu](https://docs.aws.amazon.com/kms/latest/developerguide/rotate-keys.html)

Với Google Cloud, tài liệu CMEK cũng phân biệt hành vi của từng dịch vụ tích hợp: có dịch vụ cập nhật việc bọc DEK cho dữ liệu hiện hữu, có dịch vụ chỉ dùng phiên bản mới cho dữ liệu tiếp theo hoặc tiếp tục dùng phiên bản được cấu hình trước. Cần kiểm tra đúng dịch vụ, không suy từ việc bật lịch rotation ở KMS. [Google Cloud: CMEK key rotation](https://docs.cloud.google.com/kms/docs/cmek-rotation)

### 5.3. Routine rewrap và ứng phó lộ khóa không có cùng bảo đảm

Khi chỉ cần chuyển wrapping sang KEK mới mà DEK chưa bị nghi ngờ, rewrap có thể giảm khối lượng phải xử lý so với mã hóa lại toàn bộ nội dung.

Nhưng nếu một bên đã có KEK cũ và các bản wrapped DEK cũ, họ có thể đã thu được DEK. Bọc lại cùng DEK bằng KEK mới không làm DEK đã lộ trở thành bí mật trở lại.

Trong trường hợp đó, kế hoạch cần xét tạo DEK mới và bảo vệ lại dữ liệu được quản lý, đồng thời ghi nhận giới hạn đối với những bản sao lịch sử ngoài kiểm soát.

### 5.4. Phiên bản phải được phân giải đúng khi đọc

Một số nền tảng mã hóa mang thông tin để tự chọn key material thích hợp; một số luồng yêu cầu ứng dụng lưu và truyền tham chiếu phiên bản. Metadata ứng dụng phải phù hợp hợp đồng của nền tảng.

Không dùng alias đang trỏ tới phiên bản mới như bằng chứng rằng mọi ciphertext cũ cũng được tạo bằng phiên bản mới. Nếu cần ghi phiên bản cụ thể, phải ghi giá trị phản ánh thao tác thực tế, không chỉ giá trị cấu hình mà ứng dụng dự kiến dùng.

## 6. Yêu cầu bảo mật có thể nghiệm thu

### 6.1. Yêu cầu nền tảng

```text
REQ-ROTATE-01 — Rotation theo loại khóa và phạm vi

Mỗi loại khóa thuộc phạm vi phải có policy rotation xác định mục đích,
điều kiện kích hoạt, mốc chuyển thao tác mới, cách xử lý dữ liệu lịch sử,
chủ sở hữu và bằng chứng hoàn thành.

Sau mốc hiệu lực được đặc tả, khóa cũ không được dùng cho thao tác tạo bảo vệ
mới bị policy cấm. Khả năng đọc hoặc kiểm chứng dữ liệu cũ chỉ được giữ trong
phạm vi và thời hạn cần thiết đã được phê duyệt.

Rotation không được tự động dẫn tới mất dữ liệu, giảm profile bảo vệ hoặc
hủy key material trước khi đạt điều kiện kết thúc sử dụng tương ứng.
```

### 6.2. Các yêu cầu bổ sung

| Mã | Nội dung yêu cầu | Bằng chứng nghiệm thu |
| --- | --- | --- |
| REQ-ROTATE-02 | Khóa mới phải đạt profile, nguồn sinh, quyền và khả năng phục hồi đã phê duyệt trước khi nhận dữ liệu sản phẩm | Metadata và kết quả kiểm chứng trong phạm vi chuẩn bị |
| REQ-ROTATE-03 | Mốc chuyển phiên bản phải có hiệu lực trên mọi writer/region/cache thuộc phạm vi trong giới hạn đã chọn | Kết quả thao tác mới và phiên bản thực tế |
| REQ-ROTATE-04 | Dữ liệu cũ phải đọc bằng tham chiếu đúng và quyền tương ứng; không dùng thử mọi khóa ngoài phạm vi | Các bản ghi nhiều phiên bản và trường hợp metadata sai |
| REQ-ROTATE-05 | Re-encryption hoặc rewrap phải được đặc tả riêng nếu mục tiêu yêu cầu | Danh mục dữ liệu và kết quả migration |
| REQ-ROTATE-06 | Job migration phải có checkpoint, retry an toàn và không ghi đè cập nhật mới của người dùng | Kịch bản dừng/chạy lại và cạnh tranh dữ liệu |
| REQ-ROTATE-07 | Cache và key material đã nạp phải có chính sách hiệu lực, hết hạn hoặc vô hiệu hóa phù hợp | Cache cũ, job dài và trường hợp mất kết nối control plane |
| REQ-ROTATE-08 | Ngừng dùng/hủy khóa phải dựa trên kiểm kê cả dữ liệu online, bản sao và backup còn cần thiết | Báo cáo phụ thuộc và thử phục hồi được phép |
| REQ-ROTATE-09 | Rotation do nghi ngờ lộ khóa phải có luồng khẩn cấp và mục tiêu riêng | Kịch bản ứng phó và phạm vi dữ liệu bị ảnh hưởng |
| REQ-ROTATE-10 | Lỗi khóa mới hoặc KMS không được tạo nhánh plaintext hoặc tự dùng lại khóa bị cấm | Luồng lỗi và quan sát tác động dữ liệu |

Không dùng tiêu chí “job trả thành công” thay cho những điều kiện trên. Phạm vi hoàn thành phải cho biết đã tạo khóa, chuyển writer, xử lý dữ liệu cũ hay đã đủ điều kiện hủy khóa.

## 7. Ví dụ Java: tách quyền dùng khóa theo thao tác

Ví dụ dưới đây chỉ mô hình hóa policy cho mã hóa dữ liệu. Nó không sinh key material và không thay cách thực thi trạng thái của KMS:

```java
public final class RotationPolicyExample {

    public enum Mode {
        PREPARED,
        ACTIVE_FOR_NEW,
        DECRYPT_ONLY,
        DISABLED,
        DESTROYED
    }

    public enum Operation {
        ENCRYPT_NEW,
        DECRYPT_EXISTING
    }

    private RotationPolicyExample() {
    }

    public static boolean mayUse(Mode mode, Operation operation) {
        if (mode == null || operation == null) {
            return false;
        }

        switch (mode) {
            case ACTIVE_FOR_NEW:
                return operation == Operation.ENCRYPT_NEW
                        || operation == Operation.DECRYPT_EXISTING;

            case DECRYPT_ONLY:
                return operation == Operation.DECRYPT_EXISTING;

            case PREPARED:
            case DISABLED:
            case DESTROYED:
            default:
                return false;
        }
    }
}
```

Trạng thái đầu vào phải được phân giải từ control plane hoặc nguồn policy đáng tin cậy. Không bind `Mode` từ request hoặc từ một trường metadata do caller tự khai rồi dùng nó để cấp quyền dùng khóa.

Một kết quả `true` cũng chưa cấp quyền cho mọi người. Lớp tích hợp vẫn cần kiểm tra caller, tenant, mục đích khóa, profile, giới hạn sử dụng và phiên bản có hiệu lực. Những điều kiện đó được lược khỏi ví dụ để làm rõ riêng việc ngừng ghi nhưng còn đọc.

### 7.1. Thực thi tại nơi có thể giữ hiệu lực

Nếu chỉ kiểm tra mode trong một process rồi giữ key material vô hạn, một lần cập nhật policy có thể không ngăn process đó tiếp tục mã hóa. Cần xác định nơi thực thi và cơ chế bảo đảm trạng thái không cũ quá giới hạn cho phép.

Các lựa chọn có thể gồm dịch vụ mật mã tập trung, quyền thao tác tại KMS, lease có thời hạn hoặc cơ chế vô hiệu hóa cache theo thiết kế. Không mặc định một enum hoặc một bản ghi trạng thái đã tự tạo sự cưỡng chế trên mọi instance.

### 7.2. Hành vi khi không đọc được trạng thái mới

Nếu control plane không khả dụng, policy cần nói rõ lease còn hiệu lực có được dùng tiếp hay không và trong bao lâu. Nếu đã vượt thời hạn, không tự kéo dài quyền mã hóa bằng khóa cũ để giữ khả dụng.

Đối với dữ liệu lịch sử, quyền giải mã cũng cần trạng thái và phạm vi đúng. Không mở mọi phiên bản cũ chỉ vì phiên bản hiện hành đang lỗi.

## 8. Chuyển writer và xử lý dữ liệu hiện hữu

### 8.1. Chuẩn bị trước khi kích hoạt

Trước cutover, cần xác nhận khóa mới có thể được các thành phần cần thiết sử dụng, quyền đọc/ghi đúng phạm vi và thông tin phiên bản được lưu đúng. Các reader phải hiểu định dạng và profile mà writer mới sẽ tạo.

Nếu có nhiều vùng, cần xác định khi nào mỗi vùng sẵn sàng và thành phần nào điều phối mốc chuyển. Không đánh dấu khóa mới active chỉ vì một instance thử thành công trong khi reader ở vùng khác chưa thể xử lý dữ liệu mới.

Khả năng phục hồi cũng cần được kiểm tra trong phạm vi phù hợp với loại khóa và nền tảng. Với khóa không xuất được khỏi HSM, không tự suy ra cần export key; phải dùng mô hình sao lưu, dự phòng hoặc khôi phục mà thiết kế cho phép.

### 8.2. Writer chọn phiên bản ở thời điểm phù hợp

Một request có thể được nhận trước cutover nhưng chỉ bắt đầu mã hóa sau đó. Một job có thể chờ hàng giờ trong queue. Nếu lưu sẵn `v1` trong payload job rồi dùng vô điều kiện, hệ thống có thể tiếp tục tạo ciphertext cũ lâu sau mốc.

Luồng tạo bảo vệ mới nên phân giải phiên bản đang được phép ở thời điểm mà policy xác định, hoặc dùng một tham chiếu có lease được kiểm tra đúng. Thời điểm nhận HTTP request không luôn tương đương thời điểm sử dụng khóa.

Retry cũng cần tuân thủ trạng thái hiện tại. Không giữ một lựa chọn cũ trong cơ chế retry vô hạn nếu quyền dùng phiên bản đó đã kết thúc.

### 8.3. Đọc cũ và ghi mới trong thời gian chồng lấp

Trong một lần rotation thông thường, dữ liệu `v1` có thể tiếp tục đọc còn dữ liệu mới được tạo bằng `v2`. Reader cần chọn đúng phiên bản từ envelope hoặc cơ chế được nền tảng hỗ trợ và kiểm tra quyền dùng khóa đó.

Không giải mã bản ghi `v1` bằng alias hiện đang trỏ tới `v2` nếu API yêu cầu phiên bản cụ thể. Ngược lại, nếu nền tảng tự phân giải version từ ciphertext, cần dùng đúng hợp đồng đó thay vì tự đoán hoặc sửa metadata.

### 8.4. Migration phải xử lý bản ghi theo cách có thể chạy lại

Một luồng re-encryption ứng dụng có thể gồm:

```text
Đọc snapshot của bản ghi và revision
    → xác định phạm vi/profile/phiên bản nguồn hợp lệ
    → giải mã và xác thực bằng khóa nguồn được phép
    → mã hóa bằng khóa đích được phép và nonce phù hợp
    → ghi envelope mới cùng metadata trong một cập nhật có điều kiện
    → checkpoint tiến độ hoặc phân loại lỗi để retry
```

Nếu dịch vụ hỗ trợ thao tác chuyển đổi bên trong ranh giới mật mã, có thể dùng khả năng đó theo hợp đồng để giảm việc đưa plaintext ra ngoài. Nếu plaintext phải đi qua ứng dụng, cần giới hạn vòng đời và bảo vệ nó như dữ liệu nhạy cảm, không ghi vào tệp tạm hoặc log ngoài phạm vi được phê duyệt.

Google Cloud mô tả re-encryption là công việc riêng gồm đọc bằng phiên bản cũ, bảo vệ lại bằng phiên bản đích và chỉ sau đó xem xét ngừng phiên bản nguồn. Không coi một sự kiện rotation là bằng chứng bước dữ liệu đã hoàn tất. [Google Cloud: Re-encrypting data](https://docs.cloud.google.com/kms/docs/re-encrypt-data)

### 8.5. Không ghi đè cập nhật của người dùng

Giả sử worker migration đọc revision 10; người dùng cập nhật nội dung thành revision 11; sau đó worker ghi lại ciphertext từ revision 10. Một cập nhật không điều kiện có thể làm mất thay đổi mới dù quá trình mật mã chạy đúng.

Có thể dùng một thao tác cập nhật như:

```sql
UPDATE encrypted_requirement
SET envelope = :new_envelope,
    key_version = :actual_target_version,
    revision = revision + 1
WHERE id = :resource_id
  AND tenant_id = :verified_tenant_id
  AND revision = :source_revision;
```

Nếu không có hàng được cập nhật, worker không được ghi cưỡng bức. Nó cần đọc lại hoặc phân loại theo hợp đồng cạnh tranh. `envelope` và metadata khóa phải được cập nhật nhất quán để reader không chọn sai phiên bản.

### 8.6. Idempotency, checkpoint và lỗi một phần

Một bản ghi đã đạt phiên bản đích cần được nhận diện để job có thể tiếp tục sau gián đoạn mà không làm lại vô hạn. Kiểm tra này không được thay cho việc xác thực dữ liệu và kiểm kê phần chưa xử lý.

Checkpoint cần phản ánh những cập nhật đã commit, không chỉ những bản ghi đã đọc hoặc đã đưa vào queue. Nếu migration thất bại một phần, hệ thống phải còn đọc được trạng thái hỗn hợp theo policy và cung cấp danh sách lỗi để xử lý.

Nếu đang migration sang `v2` mà policy chuyển tiếp sang `v3`, cần xác định job được tiếp tục tới đích nào. Không bỏ qua việc `v2` đã hết quyền tạo bảo vệ mới chỉ vì nó là mục tiêu được ghi từ đầu job.

## 9. Rotation khóa ký và phân phối public key

### 9.1. Bên kiểm chứng phải sẵn sàng trước khi bên ký chuyển

Với khóa ký bất đối xứng, chuyển private key mà chưa phân phối public key tương ứng có thể làm token hoặc thông điệp mới bị từ chối trên các verifier chưa cập nhật.

Một trình tự thông thường có thể là:

```text
Công bố public key mới qua kênh tin cậy
    → chờ hoặc xác nhận verifier có thể nhận key mới theo hợp đồng cache
    → bắt đầu ký mới bằng private key mới
    → ngừng ký bằng private key cũ
    → giữ khả năng kiểm chứng chữ ký cũ trong cửa sổ còn hợp lệ
    → kết thúc chấp nhận khóa cũ theo policy
```

Định danh như `kid` giúp chọn khóa trong tập đã được tin, bao gồm khi rollover. RFC 7517 mô tả mục đích này; `kid` không tự làm cho một khóa hoặc một URL khóa do bên gửi cung cấp trở thành đáng tin. [RFC 7517, mục 4.5](https://www.rfc-editor.org/rfc/rfc7517.html#section-4.5)

### 9.2. Cửa sổ giữ khóa cũ cần được tính

Đối với token ngắn hạn, cần xét thời hạn token, độ lệch đồng hồ được phép, thời điểm token cuối dùng khóa cũ và thời gian cache/phân phối của verifier. Không chỉ đặt một khoảng chồng lấp tùy ý rồi giả định mọi token hợp lệ đều còn kiểm chứng được.

Đối với tài liệu ký có giá trị lâu dài, có thể cần lưu public key và chứng cứ liên quan lâu hơn rất nhiều so với thời gian được phép ký mới. Việc chấp nhận chữ ký lịch sử còn phụ thuộc policy xác thực, thời điểm và trạng thái tin cậy tương ứng.

### 9.3. Sự cố khóa ký không giống rotation theo lịch

Nếu private key bị lộ, việc tiếp tục chấp nhận mọi chữ ký cũ trong một cửa sổ dài có thể cho phép bên có khóa tạo thêm dữ liệu giả. Cần policy ứng phó cho loại token hoặc tài liệu liên quan.

Rotation tạo khả năng ký bằng khóa mới; revocation và cách verifier cập nhật trust là công việc riêng cần được đo hiệu lực. Việc issuer đã đổi khóa không chứng minh mọi verifier đã ngừng tin khóa cũ.

## 10. Cache, backup, rollback và kết thúc vòng đời

### 10.1. Cache ảnh hưởng cả cutover lẫn thu hồi

Ứng dụng có thể cache active key reference, public key, DEK đã unwrap hoặc lease quyền sử dụng. Mỗi loại cache có tác động khác nhau và phải có quy tắc riêng.

Vô hiệu hóa quyền tại KMS không tự xóa một plaintext DEK đã được một process nạp trước đó. Nếu yêu cầu là dừng sử dụng trong một khoảng thời gian cụ thể, kiến trúc phải có khả năng cưỡng chế tương ứng và kiểm chứng nó.

Không đặt TTL chỉ theo hiệu năng rồi tuyên bố thu hồi có hiệu lực nhanh hơn TTL mà không có cơ chế khác. Cũng cần xét process bị cô lập mạng hoặc không nhận được thông báo thay đổi.

### 10.2. Backup có thể giữ phụ thuộc vào khóa cũ

Không còn bản ghi online dùng `v1` chưa đủ để hủy `v1` nếu backup còn phải phục hồi và vẫn cần khóa đó. Snapshot, object version, replica, dữ liệu lưu trữ lạnh và job đang chờ đều có thể thuộc phạm vi phụ thuộc.

Cần xác định chiến lược cho backup: giữ khóa theo thời gian phục hồi, tạo lại bản bảo vệ phù hợp hoặc chấm dứt nhu cầu giữ những bản sao theo policy. Không được thay quyền lưu dữ liệu bằng một quyết định xóa khóa không có căn cứ.

Thử khôi phục phải thực sự chứng minh có thể đọc dữ liệu theo mục tiêu phục hồi. Việc file backup tải về được chưa chứng minh phần dữ liệu mã hóa trong đó giải mã được.

### 10.3. Rollback không được làm mất đường đọc mới

Sau cutover, có thể đã xuất hiện ciphertext `v2`. Đưa writer hoặc phần mềm về phiên bản trước không được làm reader chỉ còn hiểu `v1` rồi mất khả năng đọc dữ liệu mới.

Trong rotation thông thường, một rollback được phê duyệt cần giữ tính tương thích của reader và trạng thái dữ liệu đã commit. Nếu `v1` bị nghi ngờ lộ hoặc đã hết quyền dùng, rollback không được tự kích hoạt lại việc mã hóa bằng `v1`.

### 10.4. Điều kiện disable và destruction

Trước khi ngừng khóa cũ, cần có bằng chứng cho từng lớp phụ thuộc và quyền còn cần thiết. Có thể có giai đoạn disable có kiểm soát trước destruction nếu policy cho phép, nhưng việc thử disable không thay cho kiểm kê và kế hoạch phục hồi.

Google Cloud cảnh báo hủy phiên bản còn được sử dụng có thể gây mất dữ liệu vĩnh viễn. Bước destruction phải gắn với bằng chứng đã đủ điều kiện và cơ chế phê duyệt theo hệ thống, không nằm trong nhánh cleanup tự động của một job vừa hoàn thành. [Google Cloud: Key rotation](https://docs.cloud.google.com/kms/docs/key-rotation)

Không tự thử xóa khóa sản phẩm để nghiệm thu bài học hoặc một kế hoạch chưa được phê duyệt. Các kịch bản vòng đời có thể kiểm chứng bằng tài nguyên thử nghiệm được cấp riêng cho mục đích đó.

## 11. Ma trận nghiệm thu

### 11.1. Tách từng gate hoàn thành

| Gate | Điều phải chứng minh | Điều chưa tự chứng minh |
| --- | --- | --- |
| Tạo khóa mới | Có material/phiên bản mới đạt profile và quyền | Writer đã dùng nó |
| Kích hoạt | Thao tác mới chọn đúng phiên bản theo mốc | Dữ liệu cũ đã chuyển |
| Tương thích đọc | Reader xử lý đúng dữ liệu các phiên bản còn được phép | Khóa cũ không còn phụ thuộc |
| Migration | Những bản ghi trong phạm vi đã chuyển và được kiểm chứng | Backup ngoài phạm vi cũng đã chuyển |
| Ngừng dùng | Các thao tác bị cấm không còn dùng khóa cũ | Có thể hủy mà không xét các nhu cầu còn lại |
| Kết thúc/hủy | Điều kiện phụ thuộc, thời hạn và phê duyệt đã đạt | Bản sao đã bị lộ bên ngoài đã mất hiệu lực tính toán |

### 11.2. Các tình huống trọng tâm

| Tình huống | Kỳ vọng |
| --- | --- |
| Bản ghi cũ trước cutover | Đọc được trong phạm vi policy và quyền |
| Thao tác mới sau mốc hiệu lực | Dùng phiên bản được phép thực tế, không chỉ metadata dự kiến |
| Writer còn cache cấu hình cũ | Không vượt giới hạn truyền thay đổi hoặc lease |
| Job được xếp hàng trước cutover | Chọn khóa theo thời điểm sử dụng mà hợp đồng quy định |
| Reader chưa được cấp quyền khóa mới | Phát hiện ở giai đoạn chuẩn bị hoặc xử lý lỗi an toàn; không fallback plaintext |
| Migration bị dừng rồi chạy lại | Không mất dữ liệu hoặc tạo cập nhật vô hạn |
| Người dùng sửa cùng bản ghi khi migration | Không ghi đè nội dung mới bằng snapshot cũ |
| Rewrap KEK | Bản bọc dùng KEK đích; không báo nhầm DEK hoặc dữ liệu đã thay |
| Verifier cache public key cũ | Đáp ứng kế hoạch phân phối và chồng lấp đã đặc tả |
| Khóa bị đánh dấu nghi ngờ lộ | Theo policy sự cố, không tiếp tục như rotation định kỳ |
| Backup còn dùng khóa cũ | Không hủy khóa trước khi giải quyết phụ thuộc cần giữ |
| Rollback sau khi có dữ liệu mới | Reader vẫn đọc đúng và không khôi phục quyền khóa bị cấm |

### 11.3. Kịch bản cutover cho mã hóa

```text
Given:
  v1 đang phục vụ dữ liệu cũ và v2 đã sẵn sàng.
  Mốc kết thúc thời gian chuyển đổi và cách xử lý in-flight đã được xác định.

When:
  Hệ thống kích hoạt v2 và phát sinh ghi mới từ mọi đường writer thuộc phạm vi.

Then:
  Những thao tác bị yêu cầu dùng v2 thực sự tạo dữ liệu theo v2.
  v1 không còn được dùng cho thao tác mới sau mốc tương ứng.
  Dữ liệu cũ vẫn đọc được nếu policy tiếp tục cho phép.
  Không có lỗi nào dẫn tới lưu plaintext hoặc tự dùng một khóa bị cấm.
```

### 11.4. Kịch bản kiểm chứng trước khi kết thúc khóa cũ

```text
Given:
  Migration online được báo cáo hoàn tất.
  Có danh mục backup, snapshot, replica và công việc còn chờ.

When:
  Đánh giá điều kiện ngừng sử dụng v1.

Then:
  Mỗi lớp phụ thuộc có kết quả và bằng chứng cụ thể.
  Phần chưa xử lý không bị bỏ qua chỉ vì số bản ghi online bằng không.
  Khả năng phục hồi đã được kiểm chứng theo nhu cầu giữ dữ liệu.
  Destruction chỉ được đưa vào bước riêng khi đủ điều kiện của policy.
```

## 12. Quan sát vận hành và trách nhiệm

### 12.1. Đo việc sử dụng, không chỉ đo lịch

Các chỉ số có thể gồm lần rotation gần nhất, phiên bản đang được chọn cho thao tác mới, số lần dùng phiên bản cũ theo loại thao tác, độ trễ truyền thay đổi và tiến độ migration.

Cần phân biệt một policy có lịch bật với một lần rotation thực sự đã chạy. Cũng cần phân biệt sự kiện tạo material với bằng chứng writer đã chuyển thành công.

Log có thể ghi key ID/version theo policy, operation, chủ thể sử dụng, thời điểm và kết quả. Không ghi key material, plaintext DEK hoặc nội dung dữ liệu chỉ để theo dõi rotation.

### 12.2. Phân quyền theo nhiệm vụ

Người lập policy, người vận hành dịch vụ, principal chạy migration và người phê duyệt destruction không nhất thiết cần cùng một tập quyền. Quyền quản trị vòng đời không nên tự đồng nghĩa được đọc dữ liệu nghiệp vụ.

Principal migration có thể cần quyền giải mã nguồn và mã hóa đích trong một phạm vi, thời gian cụ thể. Không cấp quyền vô hạn trên mọi khóa để tiện chạy job rồi quên thu hồi.

### 12.3. Hồ sơ hoàn thành có phạm vi

Một báo cáo nên ghi rõ rotation nào, khóa/phạm vi nào, policy nào, mốc nào đã đạt, phần dữ liệu nào đã migration và phần phụ thuộc nào còn được giữ. Lỗi hoặc ngoại lệ phải có chủ sở hữu và kế hoạch xử lý.

Không dùng từ “hoàn tất rotation” để tạo ấn tượng khóa cũ đã được hủy nếu kết quả thực tế mới chỉ là writer đã dùng khóa mới. Cách ghi phạm vi chính xác giúp đội vận hành không thực hiện bước tiếp theo dựa trên một giả định sai.

## 13. Hồ sơ yêu cầu mẫu

```text
Phạm vi:
  Khóa mã hóa nội dung yêu cầu bảo mật trong một miền dữ liệu đã xác định.

Mục tiêu:
  Chuyển thao tác tạo bảo vệ mới sang phiên bản mới theo policy.
  Giữ khả năng xử lý dữ liệu lịch sử còn được phép.

Kích hoạt:
  Theo cryptoperiod/giới hạn sử dụng được phê duyệt hoặc điều kiện sự cố.

Cutover:
  Khóa mới đạt profile và reader sẵn sàng trước khi nhận dữ liệu sản phẩm.
  Mốc hiệu lực, cache và in-flight có hợp đồng cụ thể.

Dữ liệu cũ:
  Re-encryption/rewrap được quyết định theo loại khóa và mục tiêu.
  Migration có checkpoint, retry và cập nhật chống ghi đè.
  Metadata phản ánh phiên bản thực tế, không chỉ alias hiện tại.

Kết thúc:
  Kiểm kê online, backup và các phụ thuộc còn cần thiết.
  Ngừng dùng và destruction là các gate riêng với bằng chứng tương ứng.

Sự cố và lỗi:
  Có luồng khẩn cấp khi nghi ngờ lộ khóa.
  Không có fallback plaintext hoặc tự khôi phục quyền dùng khóa bị cấm.
```

Key rotation đáp ứng mục tiêu khi vật liệu khóa mới được sử dụng đúng phạm vi và đúng mốc, dữ liệu cần giữ vẫn xử lý được, còn việc dùng khóa cũ được giới hạn và kết thúc có căn cứ. Yêu cầu bảo mật phải nối được policy, thao tác thực tế, dữ liệu phụ thuộc và bằng chứng từng gate, thay vì chỉ xác nhận một lịch tự động đã được bật.
