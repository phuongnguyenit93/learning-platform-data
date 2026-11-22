# Quản lý chi phí license Oracle và lựa chọn BYOL

Trong chương **Chi phí và quản lý năng lực**, lựa chọn mô hình license là một phần của thiết kế hạ tầng Oracle Cloud Infrastructure (OCI). Cùng một ứng dụng, tổng chi phí có thể thay đổi đáng kể khi đổi dịch vụ cơ sở dữ liệu, edition, số CPU, cấu hình dự phòng hoặc cách sử dụng license đã mua.

Bài học tập trung vào Oracle Database trên OCI, nơi quyết định **License Included** hay **Bring Your Own License (BYOL)** thường gắn trực tiếp với năng lực xử lý và kiến trúc sẵn sàng cao. Với phần mềm Oracle khác, chẳng hạn WebLogic, phải lập hồ sơ quyền sử dụng và phép tính riêng cho đúng sản phẩm; không chuyển nguyên quy tắc Oracle Database sang sản phẩm đó.

Sau bài học, người học có thể:

- Phân biệt chi phí dịch vụ OCI, quyền sử dụng phần mềm và phí support.
- Lập sổ license và đối chiếu với tài nguyên production, dự phòng, kiểm thử và chuyển đổi.
- So sánh hai mô hình bằng tổng chi phí sở hữu (TCO), số giờ sử dụng và nhu cầu mở rộng.
- Thiết kế quy trình kiểm soát license gắn với compartment, IAM, giám sát chi phí và tự động hóa triển khai.

## 1. Hai quyết định phải giải quyết đồng thời

Khi triển khai cơ sở dữ liệu, nhóm hạ tầng cần trả lời hai câu hỏi:

1. **Tài nguyên nào đáp ứng workload?** Xét độ trễ, thông lượng, dung lượng, RTO, RPO và khả năng vận hành.
2. **Quyền sử dụng nào bao phủ cấu hình đó?** Xét sản phẩm, edition, metric, số lượng, tính năng và phạm vi hợp đồng.

Một cấu hình đủ CPU vẫn có thể thiếu license. Một tập license hợp lệ vẫn có thể không phù hợp với dịch vụ hoặc edition mà ứng dụng cần. Vì vậy, quyết định tài chính phải dựa trên cấu hình đã đáp ứng yêu cầu kỹ thuật và có căn cứ về quyền sử dụng.

### License Included và BYOL

| Khía cạnh | License Included | BYOL |
|---|---|---|
| Nguồn quyền sử dụng phần mềm | Đi cùng dịch vụ đã chọn, trong phạm vi offering | Từ license đủ điều kiện của tổ chức |
| Khoản cần mô hình hóa | Mức giá dịch vụ có license và các khoản phát sinh | Giá BYOL, support của license mang sang và các khoản phát sinh |
| Dữ liệu cần quản lý | Dịch vụ, edition, tính năng, mức sử dụng | Các dữ liệu bên trái cộng hồ sơ license và phân bổ |
| Câu hỏi quyết định | Offering đã bao phủ yêu cầu chưa? | License hiện có có thực sự bao phủ cấu hình đích không? |

Oracle mô tả BYOL to PaaS là sử dụng quyền phần mềm hiện có, với support phần mềm qua hợp đồng support tương ứng; nghĩa vụ trả support hằng năm vẫn tiếp tục. BYOL vì thế không đồng nghĩa với chi phí phần mềm bằng không. Xem [Oracle BYOL FAQ](https://www.oracle.com/cloud/bring-your-own-license/faq/).

Trong thực hành, hãy giữ riêng ba con số: hóa đơn OCI, chi phí license/support ngoài hóa đơn OCI và chi phí nhân sự vận hành. Chỉ nhìn hóa đơn cloud có thể làm phương án BYOL trông rẻ hơn tổng chi phí thực tế.

## 2. Xác định đúng nơi chạy Oracle Database

Trước khi tính tiền, ghi rõ dịch vụ đích. “Chạy Oracle trên OCI” chưa đủ để chọn một quy tắc cấp phép.

| Phương án triển khai | Nội dung cần xác định trước khi so sánh |
|---|---|
| Oracle Base Database Service | Edition, mô hình CPU, shape, dung lượng, license model, cấu hình HA |
| Autonomous Database | Loại workload, mô hình ECPU/OCPU, edition dùng cho BYOL, autoscaling, dự phòng |
| Exadata Database Service | Loại triển khai, phần hạ tầng và phần database được tính riêng, CPU được kích hoạt, tính năng sử dụng |
| Tự cài Oracle Database trên OCI Compute | Phạm vi máy/CPU phải cấp phép, trách nhiệm vận hành và quyền phần mềm tương ứng |

Phân biệt managed database với tự cài trên Compute đặc biệt quan trọng. Không lấy đơn giá máy ảo Compute để đại diện cho toàn bộ chi phí managed database; cũng không lấy quyền bổ sung của một dịch vụ database để gán cho mọi máy ảo trong tenancy.

Với tài liệu cấp phép, phải đối chiếu đúng phiên bản Oracle Database, offering và tính năng. Oracle cung cấp bảng quyền theo offering và mục **Special License Rights** trong [Database Licensing Information](https://docs.oracle.com/en/database/oracle/oracle-database/26/dblic/Licensing-Information.html).

Một bản mô tả cấu hình tối thiểu nên có dạng:

```text
Workload: hệ thống đơn hàng
Dịch vụ đích: Oracle Base Database Service
Edition: Enterprise Edition
Mô hình CPU: ghi đúng ECPU hoặc OCPU của cấu hình lựa chọn
Production: năng lực nền, năng lực đỉnh, lịch sử sử dụng
HA/DR: tài nguyên tại chỗ và tài nguyên vùng dự phòng
Tính năng: liệt kê riêng option/management pack thực sự cần
License model dự kiến: License Included hoặc BYOL
Hồ sơ quyền sử dụng: mã tham chiếu nội bộ và người chịu trách nhiệm
```

VCN và subnet xác định kết nối mạng; compartment và IAM giúp tổ chức, phân quyền tài nguyên. Những thành phần này hỗ trợ quản trị nhưng không thay thế hồ sơ quyền sử dụng phần mềm.

## 3. Lập sổ license trước khi chọn BYOL

Sổ license là bảng đối chiếu giữa quyền tổ chức đang có và nơi quyền đó đang được sử dụng. Không nên bắt đầu bằng câu “công ty đã mua Oracle rồi”; phải xác định chính xác đã mua gì và đang phân bổ ở đâu.

### 3.1. Hồ sơ cần thu thập

| Nhóm thông tin | Nội dung cần ghi nhận | Mục đích |
|---|---|---|
| Sản phẩm và edition | Tên chương trình, edition, phiên bản được sử dụng | Tránh dùng quyền của sản phẩm/edition khác |
| Metric và số lượng | Processor, Named User Plus hoặc metric theo hợp đồng | Chọn đúng phép tính |
| Loại quyền | Full Use, quyền gắn với ứng dụng, quyền có giới hạn khác | Xác định workload được phép sử dụng |
| Phạm vi hợp đồng | Pháp nhân, lãnh thổ và các hạn chế liên quan | Kiểm tra môi trường đích có thuộc phạm vi |
| Support | Trạng thái, kỳ hạn, chi phí và bộ license liên quan | Xác định điều kiện BYOL và dòng tiền |
| Option/management pack | Quyền riêng, số lượng và nơi đang sử dụng | Tránh chỉ kiểm tra license database nền |
| Phân bổ hiện tại | On-premises, OCI, môi trường dự phòng, kiểm thử | Phát hiện phân bổ trùng |
| Bằng chứng | Hợp đồng, ordering document, phụ lục và xác nhận áp dụng | Giải thích được căn cứ của quyết định |

**Processor** và **Named User Plus (NUP)** là hai metric khác nhau. NUP không đơn thuần là số người đăng nhập đồng thời; cần kiểm tra định nghĩa người/thiết bị được phép truy cập, cơ chế multiplexing và số lượng tối thiểu. Các quyền Full Use, Application Specific và Embedded cũng có phạm vi khác nhau. Xem phần khái niệm trong [Oracle Software Licensing Basics](https://www.oracle.com/a/ocom/docs/corporate/oracle-software-licensing-basics.pdf).

Không suy ra điều kiện BYOL chỉ từ việc có tài khoản My Oracle Support hoặc có bộ cài phần mềm. Cần liên kết được license cụ thể với điều khoản áp dụng và trạng thái support.

### 3.2. Quyền chưa dùng và quyền có thể mang sang

Ví dụ, sổ tài sản ghi sáu license không có nghĩa cả sáu đều sẵn sàng cho OCI. Một phần có thể đang phục vụ production tại trung tâm dữ liệu; phần khác có giới hạn ứng dụng hoặc chưa đủ hồ sơ xác nhận.

Một cách tổ chức bảng phân bổ nội bộ:

```text
Tổng quyền đã được xác minh
- quyền đang phân bổ cho hệ thống hiện hữu
- quyền đang dành cho môi trường chuyển đổi chạy song song
- quyền đã cam kết cho dự án khác
= quyền còn có thể xem xét phân bổ
```

Đây là công thức quản trị danh mục, không phải quy tắc chuyển đổi license của Oracle. Mỗi số trừ phải có đối tượng, thời điểm bắt đầu/kết thúc và người chịu trách nhiệm. Chỉ giải phóng một phân bổ khi đã có bằng chứng môi trường cũ đáp ứng điều kiện kết thúc sử dụng tương ứng.

Với ULA, quyền giới hạn theo ứng dụng hoặc các thỏa thuận đặc biệt, cần lưu kết luận theo chính văn bản áp dụng. Không biến tên loại hợp đồng thành giả định “được dùng mọi nơi với số lượng không giới hạn”.

## 4. Chuyển năng lực OCI thành nhu cầu license

### 4.1. Không đồng nhất ECPU, OCPU, vCPU và Processor license

Các tên trên thuộc những ngữ cảnh đo lường khác nhau. Khi lập phép tính, ghi rõ:

- Đơn vị tài nguyên của dịch vụ: ECPU, OCPU hoặc đơn vị khác.
- Metric license đang có.
- Hệ số chuyển đổi của đúng dịch vụ/SKU và edition.
- Quy tắc làm tròn, giới hạn và yêu cầu tối thiểu.
- Quyền cho option/pack hoặc dự phòng cần kiểm tra riêng.

Không lấy hệ số của dịch vụ cũ, của hyperscaler khác hoặc của môi trường tự cài để áp dụng cho managed database trên OCI.

Ví dụ có phạm vi cụ thể: phần BYOL cho **Oracle Base Database Service – BYOL – x86 – ECPU, B112728**, trong Service Descriptions có hiệu lực ngày 05/11/2026, quy định một supported Processor license của Enterprise Edition tương ứng tối đa 8 ECPU. Hệ số này không phải quy tắc chung cho mọi sản phẩm. Xem [Universal Credits Service Descriptions](https://www.oracle.com/contracts/docs/paas_iaas_universal_credits_3940775.pdf), mục BYOL Non-Autonomous Database Cloud Services.

### 4.2. Ví dụ phân bổ theo hệ số đã xác minh

Giả sử dự án dùng đúng dịch vụ và điều kiện EE nêu trên, có bốn Processor license đủ điều kiện và không còn phân bổ ở hệ thống khác. Chỉ xét license database nền trong phép tính này:

| Hạng mục | Năng lực cần bao phủ | Processor license theo hệ số 8 ECPU |
|---|---:|---:|
| Production ở mức nền | 16 ECPU | 2 |
| DR đã xác định cần bao phủ | 8 ECPU | 1 |
| Phần tăng thêm cho đỉnh production | 8 ECPU | 1 |
| Tổng khi production đạt đỉnh | 32 ECPU | 4 |

Ở trạng thái đỉnh, production sử dụng 24 ECPU và DR sử dụng 8 ECPU. Phần “tăng thêm” trong bảng là năng lực dự kiến phải bao phủ khi mở rộng, không phải một tài nguyên thứ ba đang chạy.

Với một cấu hình riêng lẻ có cùng điều kiện chuyển đổi:

```text
Số Processor license cần xem xét = ceil(ECPU cần bao phủ / 8)
```

Khi có nhiều tài nguyên, phải áp dụng quy tắc phân bổ/làm tròn của điều khoản tương ứng; không tự gộp các phần lẻ của nhiều database thành một kho dùng chung. Ví dụ trên dùng các số chia hết để tập trung vào việc phân bổ.

Nếu nhóm phát triển tạo thêm một bản clone cần 8 ECPU trong lúc production đang ở đỉnh, nhu cầu thành 40 ECPU và vượt phân bổ bốn license. Một phép kiểm tra trước triển khai phải phát hiện tình huống này, dù hóa đơn tháng trước vẫn còn thấp.

### 4.3. Giai đoạn chuyển đổi dễ gây phân bổ trùng

Giả sử bốn license vừa nêu vẫn đang được tính cho hệ thống cũ trong thời gian chạy song song. Không thể chỉ đổi nhãn phân bổ sang OCI rồi coi hệ thống cũ đã biến mất.

Kế hoạch migration cần ghi rõ:

1. Khoảng thời gian hai môi trường cùng tồn tại.
2. Quyền hoặc mô hình tính phí bao phủ từng môi trường trong khoảng đó.
3. Thời điểm cutover, rollback và kết thúc chạy song song.
4. Bằng chứng thu hồi tài nguyên và cập nhật sổ phân bổ.

Nếu không có quyền chạy đồng thời phù hợp, nhóm phải điều chỉnh lịch, bổ sung quyền hoặc chọn mô hình dịch vụ thích hợp cho giai đoạn chuyển tiếp. Không mặc định có một khoảng thời gian miễn phí chung cho mọi migration.

## 5. Kiểm tra edition, option và management pack

Hai hệ thống cùng ghi “Enterprise Edition” vẫn có thể cần tập quyền khác nhau. Các yêu cầu như phân vùng dữ liệu, nén, bảo mật, clustering, chẩn đoán hoặc truy vấn trên standby cần được đối chiếu với offering và phiên bản cụ thể.

Oracle có cấp một số quyền bổ sung cho BYOL trên các dịch vụ database được chỉ định. Chẳng hạn, EE BYOL trên Base Database Service được nêu với quyền dùng Diagnostics Pack và Tuning Pack. Đây không phải quyền bao trùm cho mọi option hoặc cho database tự cài trên Compute. Đối chiếu mục **Special License Rights** trong [Database Licensing Information](https://docs.oracle.com/en/database/oracle/oracle-database/26/dblic/Licensing-Information.html).

Một bảng kiểm tính năng hữu ích hơn một ô “đã có license Oracle”:

| Tính năng cần dùng | Lý do kỹ thuật | Căn cứ quyền | Phạm vi được áp dụng | Kết luận |
|---|---|---|---|---|
| Tính năng A | Đáp ứng truy vấn của ứng dụng | Quyền đã mua hoặc quyền của offering | Dịch vụ, edition, phiên bản cụ thể | Đủ/chưa đủ dữ kiện |
| Tính năng B | Đáp ứng vận hành hoặc HA | Điều khoản tương ứng | Production, standby hoặc môi trường khác | Đủ/cần bổ sung |

Đối với database hiện hữu, kết hợp kiểm kê cấu hình, lịch sử sử dụng tính năng và hồ sơ quyền. Một tính năng xuất hiện trong bộ cài hoặc có thể bật bằng tham số không chứng minh tổ chức đã có quyền sử dụng nó.

Nếu tối ưu chi phí bằng cách giảm edition hoặc bỏ option, phải kiểm tra ứng dụng có còn hoạt động đúng và đáp ứng SLA hay không. Tiết kiệm license nhưng làm mất yêu cầu phục hồi hoặc hiệu năng không tạo ra một phương án triển khai tương đương.

## 6. Gắn license với autoscaling, HA và DR

### 6.1. Nhu cầu chi phí và nhu cầu quyền sử dụng có cách nhìn khác nhau

Để ước lượng hóa đơn, thường cần tích lũy lượng tài nguyên theo thời gian:

```text
Đơn vị tài nguyên-giờ = tổng(năng lực được tính phí trong khoảng × số giờ khoảng đó)
```

Để kiểm tra BYOL, phải xác định năng lực nào cần quyền bao phủ theo quy tắc dịch vụ. CPU trung bình trong tháng không chứng minh đã đủ license cho cấu hình tại lúc mở rộng.

Vì vậy, hồ sơ capacity nên có cả mức nền, mức đỉnh được phép và thời gian dự kiến ở từng mức. Khi thay đổi autoscaling, phải cập nhật đồng thời mô hình chi phí và kiểm tra phân bổ license.

### 6.2. Autonomous có cơ chế BYOL ECPU limit cần xem riêng

Tài liệu Autonomous ECPU mô tả tùy chọn giới hạn số ECPU được BYOL bao phủ cho EE. API cũng mô tả phần vượt `byolComputeCountLimit` được xem là License Included và tính phí. Chỉ áp dụng cơ chế này ở offering hỗ trợ; không suy ra mọi DB system đều tự xử lý phần thiếu license như vậy. Xem [hướng dẫn Autonomous ECPU](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/autonomous-update-license.html) và [mô tả trường BYOL limit trong API model](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/database/models/oci.database.models.UpdateAutonomousDatabaseDetails.html).

Khi dùng giới hạn BYOL, cần quản trị hai ranh giới: số ECPU có quyền bao phủ và chi phí phần vượt giới hạn. Nếu giới hạn chỉ điều khiển mô hình tính phí, đừng coi nó là bằng chứng tài nguyên sẽ ngừng mở rộng ở mức đó. Kiểm tra thêm hành vi autoscaling, edition, standby và cấu hình riêng của tài nguyên.

### 6.3. Không bỏ sót các bản sao và môi trường dự phòng

Danh sách rà soát năng lực nên bao gồm:

- Primary và các node phục vụ HA.
- Standby ở cùng vùng hoặc vùng khác.
- Môi trường DR được mở để diễn tập hoặc phục vụ báo cáo.
- Clone cho UAT, kiểm thử hiệu năng và xử lý sự cố.
- Môi trường cũ còn hoạt động trong thời gian migration hoặc rollback.

Oracle phân biệt failover dạng cluster dùng chung lưu trữ với các hình thức copying/synchronizing/mirroring. Quy tắc failover mười khoảng 24 giờ có điều kiện cụ thể; không thể dùng nó như quyền miễn phí chung cho mọi standby hoặc DR trên cloud. Xem [Licensing Data Recovery Environments](https://www.oracle.com/a/ocom/docs/data-recovery-licensing-070587.pdf).

Giảm cấu hình DR để tiết kiệm phải đi cùng phép kiểm tra khả năng phục hồi. Cần biết khi sự cố xảy ra, tài nguyên dự phòng có thể nâng lên mức nào, quyền nào bao phủ mức đó và chi phí vận hành trong sự cố được dự trù ra sao.

## 7. So sánh bằng TCO và điểm hòa vốn

### 7.1. Chuẩn hóa hai phương án trước khi tính

Hai báo giá chỉ so sánh được khi đáp ứng cùng yêu cầu. Ghi rõ dịch vụ, edition, tính năng, hiệu năng, số giờ sử dụng, storage, backup, HA/DR, vùng triển khai và thời hạn phân tích.

Nếu hai offering có hiệu năng khác nhau, cần đo workload để tìm cấu hình đáp ứng cùng SLA. Không ép chúng có cùng số CPU rồi kết luận phương án có đơn giá CPU thấp hơn sẽ rẻ hơn.

Một mô hình tài chính đơn giản:

```text
TCO trong kỳ = chi phí dịch vụ OCI
             + support/license ngoài hóa đơn OCI
             + chi phí mua bổ sung được phân bổ trong kỳ
             + chi phí vận hành
             + chi phí chuyển đổi được phân bổ trong kỳ
```

Các khoản có thể nằm trong chi phí OCI gồm compute/database meter, storage, backup, lưu lượng và hạ tầng dành riêng. Tách khoản nào đã nằm trong đơn giá để tránh cộng hai lần.

Với hợp đồng có cam kết chi tiêu hoặc tín dụng, nên lập thêm góc nhìn dòng tiền và mức tiêu thụ cam kết. Credit làm thay đổi cách thanh toán hoặc phân bổ chi phí, không tự chứng minh đã đủ quyền BYOL.

### 7.2. Ví dụ dùng hoàn toàn giá giả định

Giả sử hai cấu hình đạt cùng yêu cầu, cùng dùng 8 đơn vị tài nguyên tính phí, ký hiệu `U`. `U` chỉ là đơn vị của bài toán; không dùng ví dụ này để suy ra ECPU bằng OCPU hoặc Processor license. Các đơn giá sau **không phải bảng giá Oracle**.

| Biến | Giá trị giả định |
|---|---:|
| Đơn giá License Included | 1,20 USD/U-giờ |
| Đơn giá BYOL | 0,45 USD/U-giờ |
| Thời gian sử dụng trong tháng | 730 giờ |
| Storage, backup và các khoản OCI chung | 500 USD/tháng |
| Support riêng của phương án BYOL | 3.500 USD/tháng |
| Vận hành License Included | 150 USD/tháng |
| Vận hành BYOL | 220 USD/tháng |
| Mua license bổ sung và chuyển đổi | 0 USD trong ví dụ |

Giả định quan trọng của phép so sánh: 3.500 USD support là chi phí chênh lệch thực sự giữa hai phương án. Chỉ dùng giả định này nếu phương án License Included cho phép loại bỏ khoản support đó sau khi kiểm tra điều kiện hợp đồng. Nếu tổ chức vẫn phải trả support ở cả hai phương án, phải đưa nó vào cả hai cột hoặc loại khỏi phần tính chênh lệch.

Kết quả ở 730 giờ:

| Khoản chi | License Included | BYOL |
|---|---:|---:|
| Tài nguyên dịch vụ | 8 × 730 × 1,20 = 7.008 | 8 × 730 × 0,45 = 2.628 |
| Chi phí OCI chung | 500 | 500 |
| Support ngoài hóa đơn OCI trong phạm vi so sánh | 0 | 3.500 |
| Vận hành | 150 | 220 |
| **Tổng USD/tháng** | **7.658** | **6.848** |

BYOL giảm 810 USD/tháng trong điều kiện giả định này. Nếu chỉ nhìn chênh lệch hóa đơn dịch vụ 4.380 USD, nhóm sẽ bỏ sót support và phần vận hành tăng thêm.

### 7.3. Điểm hòa vốn phụ thuộc số giờ chạy

Với năng lực cố định và chi phí OCI chung giống nhau:

```text
Hòa vốn khi:
n × H × (p_LI - p_BYOL)
= (support_BYOL - support_LI)
  + (vận_hành_BYOL - vận_hành_LI)
  + các chi phí chênh lệch khác trong kỳ
```

Áp dụng số giả định:

```text
H = (3.500 + 220 - 150) / (8 × (1,20 - 0,45))
  = 3.570 / 6
  = 595 giờ/tháng
```

| Thời gian sử dụng | TCO License Included | TCO BYOL | Phương án thấp hơn theo giả định |
|---|---:|---:|---|
| 160 giờ/tháng | 2.186 USD | 4.796 USD | License Included, thấp hơn 2.610 USD |
| 595 giờ/tháng | 6.362 USD | 6.362 USD | Hòa vốn |
| 730 giờ/tháng | 7.658 USD | 6.848 USD | BYOL, thấp hơn 810 USD |

Đây là lý do một môi trường chạy liên tục và một môi trường dùng vài giờ mỗi ngày có thể dẫn đến hai quyết định khác nhau, dù cùng workload và cùng đơn giá.

Nếu có autoscaling, thay `n × H` bằng tổng tài nguyên-giờ từng khoảng. Nếu có phần vượt BYOL được tính License Included ở dịch vụ hỗ trợ, tách riêng lượng sử dụng và đơn giá của hai phần.

### 7.4. Phân biệt chi phí đã phát sinh và chi phí tương lai

Giá mua license từ nhiều năm trước có thể là chi phí đã phát sinh. Khi quyết định triển khai mới, cần nhìn dòng tiền tương lai có thể thay đổi giữa các lựa chọn. Khi báo cáo đầy đủ chi phí cho đơn vị kinh doanh, tổ chức vẫn có thể phân bổ giá trị license theo chính sách kế toán nội bộ.

Không cộng nguyên giá mua vào mỗi tháng. Nếu cần mô hình TCO nhiều năm, ghi rõ kỳ phân bổ, support từng năm, chi phí bổ sung, thay đổi quy mô và các giả định tăng giá. Đồng thời đánh giá chi phí cơ hội: dùng license cho dự án này có khiến dự án khác phải mua thêm hay không.

Việc dừng tài nguyên có thể thay đổi chi phí dịch vụ theo quy tắc của offering, nhưng không mặc nhiên chấm dứt phí support của license đã mua. Tiết kiệm từ lịch dừng phải được tính trên các khoản thực sự thay đổi.

## 8. Chọn mô hình theo bằng chứng

Bảng sau là khung ra quyết định, không phải kết luận áp dụng cho mọi hợp đồng:

| Tình huống | Hướng cần đánh giá trước | Bằng chứng cần có |
|---|---|---|
| Chưa có license phù hợp, dự án ngắn hạn | License Included | Offering đáp ứng yêu cầu và dự toán theo thời gian chạy |
| Có license đủ điều kiện chưa phân bổ, workload ổn định | BYOL | Hồ sơ quyền, support, phép chuyển đổi và TCO |
| Có license nhưng vẫn cần cho on-premises | Phương án chạy song song hoặc chuyển đổi theo giai đoạn | Phân bổ theo từng thời điểm và quyền cho phần chồng lấn |
| Workload tăng đột biến vượt năng lực đã bao phủ | Giới hạn mở rộng hoặc cơ chế tính phí vượt BYOL nếu dịch vụ hỗ trợ | Hành vi dịch vụ, giới hạn quyền và dự báo hóa đơn |
| License có hạn chế ứng dụng/pháp nhân hoặc hồ sơ chưa rõ | Hoàn tất xác minh quyền trước quyết định BYOL | Kết luận có căn cứ theo văn bản áp dụng |

Một quyết định có thể dùng License Included cho tài nguyên này và BYOL cho tài nguyên khác. Mỗi tài nguyên vẫn cần cấu hình mô hình license và hồ sơ riêng; cách chia danh mục không chứng minh có thể trộn hai mô hình trong một tài nguyên bất kỳ.

Nên ghi quyết định dưới dạng bản ghi ngắn gồm cấu hình đích, phương án được chọn, TCO, phân bổ license, người xác nhận và điều kiện phải xem xét lại. Ví dụ, tăng CPU tối đa, bật tính năng mới hoặc thêm standby là các sự kiện có thể làm quyết định cũ không còn phù hợp.

## 9. Đưa kiểm soát license vào vận hành OCI

### 9.1. Phân vai và lưu bằng chứng

| Vai trò | Trách nhiệm chính trong quy trình |
|---|---|
| Chủ ứng dụng/DBA | Xác định workload, edition, tính năng, HA và DR |
| Nhóm nền tảng OCI | Kiểm kê tài nguyên, kiểm soát cấu hình, compartment và IAM |
| Quản lý tài sản phần mềm/mua sắm | Xác minh quyền, support và phân bổ license |
| FinOps/tài chính | Theo dõi TCO, dự toán, hóa đơn và phân bổ chi phí |

Có thể dùng tag nội bộ để liên kết tài nguyên với cost center, môi trường, chủ sở hữu và mã hồ sơ license. Ví dụ, namespace do tổ chức tự định nghĩa `Governance` có khóa `LicenseAllocationRef` trỏ đến một bản ghi được quản lý. Tag chỉ là liên kết quản trị; giá trị ghi “BYOL-approved” không tự tạo ra quyền sử dụng.

Không đặt toàn bộ hợp đồng hoặc thông tin nhạy cảm vào tag. Lưu bằng chứng trong kho có kiểm soát truy cập và chỉ đưa mã tham chiếu cần thiết vào tài nguyên.

### 9.2. Kiểm soát trước thay đổi

Trong pipeline hạ tầng hoặc quy trình thay đổi, yêu cầu kiểm tra khi:

- Tạo mới hoặc clone database.
- Chuyển sang BYOL hoặc thay edition.
- Tăng CPU, tăng giới hạn autoscaling hoặc thay shape.
- Thêm node, standby, vùng DR hoặc môi trường kiểm thử.
- Bật tính năng có thể làm thay đổi yêu cầu quyền sử dụng.

Một logic kiểm tra nội bộ có thể được mô tả như sau:

```text
Đọc cấu hình dự kiến và hồ sơ phân bổ.
Xác định dịch vụ, edition, metric và quy tắc áp dụng.
Tính nhu cầu sau thay đổi cho mọi môi trường liên quan.
Kiểm tra license nền, option/pack và support.
So sánh với quyền còn có thể phân bổ.
Nếu thiếu dữ kiện hoặc vượt quyền: chặn thay đổi và chuyển người phụ trách.
Nếu đủ căn cứ: lưu kết quả, thời điểm và mã yêu cầu thay đổi.
```

Đây là thiết kế quy trình của tổ chức. Không giả định một tag, policy IAM hoặc công cụ IaC tự biết các điều khoản trong hợp đồng Oracle. IAM giới hạn ai được thực hiện thao tác; sổ license và quy trình đối chiếu quyết định thao tác đó có được quyền phần mềm bao phủ hay không.

### 9.3. Theo dõi sau triển khai

Thiết kế đối chiếu định kỳ giữa ba nguồn:

1. **Tài nguyên thực tế:** license model, CPU, autoscaling, bản sao và tính năng.
2. **Chi phí:** tài nguyên nào phát sinh khoản nào và lệch dự toán bao nhiêu.
3. **Sổ quyền:** license nào đang phân bổ, support còn hiệu lực đến đâu.

Cảnh báo chi phí giúp phát hiện thay đổi hóa đơn, nhưng không chứng minh đã đủ license. Ngược lại, một tài nguyên có quyền sử dụng hợp lệ vẫn có thể vượt ngân sách. Mỗi cảnh báo cần có người nhận và hành động cụ thể, chẳng hạn đối chiếu clone mới hoặc xác minh phần mở rộng gần đây.

Trong lịch vận hành, có thể rà soát tài nguyên thường xuyên, đối chiếu chi phí theo kỳ thanh toán và kiểm tra các mốc gia hạn support theo lịch hợp đồng. Tần suất nên phù hợp tốc độ thay đổi của hệ thống.

## 10. Thực hành kiểm kê cấu hình và lập đề xuất

Phần này dùng tài nguyên sẵn có với quyền đọc phù hợp. Không cần tạo database mới hoặc chuyển license model để hoàn thành bài thực hành. Nếu chưa có môi trường OCI, sử dụng bộ cấu hình giả định ở phần 4 và bảng giá giả định ở phần 7 để thực hiện bước tính toán.

### Bước 1: Đọc cấu hình tài nguyên

Với OCI CLI đã cấu hình profile, region và quyền truy cập, đọc một Base Database DB system trong PowerShell:

```powershell
$dbSystemId = 'ocid1.dbsystem.REPLACE_WITH_YOUR_RESOURCE_OCID'
oci db system get --db-system-id $dbSystemId --output json
```

Đối chiếu định danh, compartment, shape, edition, cấu hình CPU và `license-model`. Lệnh này dùng cho loại tài nguyên DB system phù hợp, không đại diện cho mọi tài nguyên Exadata. Tham khảo [OCI CLI: db system get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/db/system/get.html).

Với Autonomous Database:

```powershell
$autonomousDatabaseId = 'ocid1.autonomousdatabase.REPLACE_WITH_YOUR_RESOURCE_OCID'
oci db autonomous-database get --autonomous-database-id $autonomousDatabaseId --output json
```

Đọc license model, mô hình/năng lực CPU và các thiết lập mở rộng, BYOL limit hoặc dự phòng được trả về cho offering. Một trường không có hoặc giá trị `null` cần được đối chiếu với tài liệu tương ứng. Tham khảo [OCI CLI: autonomous-database get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/db/autonomous-database/get.html).

JSON cấu hình cho biết trạng thái tài nguyên; nó không xác nhận hợp đồng của tổ chức đã bao phủ trạng thái đó. Cần kết hợp kết quả với sổ license và dữ liệu chi phí.

### Bước 2: Dựng bảng năng lực theo kịch bản

Ghi mức nền và đỉnh cho production, DR và môi trường kiểm thử. Tạo ít nhất ba cột thời điểm: vận hành bình thường, cao điểm và migration chạy song song.

Với từng cột, tính lại nhu cầu license theo quy tắc đã xác minh. Đánh dấu hạng mục chưa đủ dữ kiện thay vì tự điền một hệ số chung. Ghi rõ phần nào được BYOL bao phủ và phần nào có mô hình tính phí khác nếu offering hỗ trợ.

### Bước 3: Tính TCO cho hai lựa chọn

Sử dụng đơn giá và điều khoản phù hợp tại thời điểm đánh giá; trong môi trường học có thể dùng giá giả định của bài. Tách chi phí dịch vụ, support, vận hành, mua bổ sung và migration. Tính cả số giờ sử dụng thực tế và độ nhạy khi nhu cầu tăng.

Kết quả cần chỉ ra phương án thấp hơn ở mức nền, phương án ở đỉnh và khoản chênh lệch nào có thể thay đổi kết luận. Nếu chưa biết liệu có thể giảm support hay không, trình bày hai kịch bản thay vì chọn một giả định có lợi cho BYOL.

### Bước 4: Chuẩn bị thay đổi nếu chọn mô hình khác

Với Base Database DB system được hỗ trợ, Oracle hướng dẫn mở chi tiết tài nguyên, chọn **Actions → Update license type**, chọn mô hình rồi lưu/xác nhận. Thay đổi này ảnh hưởng metering của hóa đơn. Xem [Manage Licenses on a DB System](https://docs.oracle.com/en/cloud/paas/base-database/guide/dbs-licenses.html).

Trước thao tác thực tế, hoàn tất căn cứ quyền sử dụng, phân bổ, dự báo chi phí và quy trình thay đổi của tổ chức. Sau thao tác, đối chiếu trạng thái trả về, dữ liệu chi phí của kỳ liên quan và sổ phân bổ. Việc Console chấp nhận một lựa chọn không thay thế kết luận về quyền sử dụng.

Đầu ra thực hành là một đề xuất gồm bảng tài nguyên, bảng phân bổ quyền, hai phương án TCO và điều kiện cần đáp ứng trước thay đổi. Không cần thực hiện thao tác ghi trên OCI chỉ để chứng minh đã hiểu cách lựa chọn.

## 11. Những sai lầm làm sai quyết định chi phí

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ so sánh đơn giá compute | Bỏ sót support, storage, DR và vận hành | Chuẩn hóa cấu hình rồi tính TCO |
| Coi mọi license Oracle có thể dùng thay nhau | Sai sản phẩm, edition hoặc phạm vi quyền | Đối chiếu từng dòng quyền với dịch vụ đích |
| Dùng CPU trung bình để chứng minh đủ BYOL | Bỏ sót cấu hình đỉnh hoặc autoscaling | Kiểm tra nhu cầu cần bao phủ theo từng kịch bản |
| Cấp cùng license cho on-premises và OCI mà chưa có căn cứ | Phân bổ trùng trong migration | Lập lịch chạy song song và hồ sơ quyền tương ứng |
| Mặc định DR hoặc non-production được miễn license | Thiếu quyền cho bản sao và diễn tập | Kiểm kê từng môi trường, kiểm tra điều kiện áp dụng |
| Suy mọi option đều cần mua riêng hoặc đều đã bao gồm | Mua thừa hoặc thiếu quyền sử dụng | Đối chiếu offering, phiên bản và quyền bổ sung cụ thể |
| Coi trường `license-model` là chứng nhận hợp lệ | Cấu hình và hồ sơ quyền không khớp | Đối chiếu tài nguyên với sổ license và bằng chứng |
| Dừng máy rồi xóa toàn bộ support khỏi dự toán | Đánh giá quá cao mức tiết kiệm | Tách khoản biến đổi theo sử dụng và nghĩa vụ theo hợp đồng |
| Tối ưu license bằng cách giảm HA không kiểm tra SLA | Không đạt yêu cầu phục hồi | Kiểm chứng RTO/RPO và năng lực khi sự cố |

Quyết định cần được xem xét lại khi workload, cấu hình, quyền sử dụng hoặc giá thay đổi. Một bản ghi có thể giải thích được **tài nguyên nào được bao phủ bởi quyền nào, ở thời điểm nào và với tổng chi phí bao nhiêu** là nền tảng để vận hành BYOL có kiểm soát trên OCI.
