# Phân tích thay đổi đồng thời để tìm phần gắn kết chặt

## 1. Bối cảnh và mục tiêu

Khi phân rã một hệ thống thành các vi dịch vụ (microservices), ranh giới hợp lý không nhất thiết trùng với package, bảng dữ liệu, tầng kỹ thuật hay tên của từng chức năng trên giao diện. Một dấu hiệu đáng quan tâm là: **những phần nào của hệ thống thường phải thay đổi cùng nhau để hoàn thành một yêu cầu nghiệp vụ?**

Phân tích thay đổi đồng thời (*co-change analysis*, còn gọi là *logical/temporal coupling analysis*) khai thác lịch sử thay đổi mã nguồn để tìm các thành phần có xu hướng được sửa trong cùng commit, pull request hoặc công việc. Hai thành phần liên tục thay đổi cùng nhau có thể chia sẻ quy tắc nghiệp vụ, dữ liệu, giao diện không ổn định hoặc một trách nhiệm chưa được phân rã rõ. Chúng là ứng viên cần xem xét để đặt gần nhau trong một ranh giới module hoặc dịch vụ.

Mục tiêu của bài học:

- Hiểu thế nào là thay đổi đồng thời, gắn kết nội bộ (*cohesion*) và phụ thuộc giữa các thành phần (*coupling*).
- Thu thập một tập thay đổi đủ tin cậy; phân biệt bằng chứng từ Git với nguyên nhân thực sự của thay đổi.
- Tính tần suất thay đổi chung và các chỉ số có chuẩn hóa để so sánh những cặp thành phần.
- Nhìn ra cụm mã có gắn kết chặt, đánh giá ranh giới ứng viên theo nghiệp vụ và giao dịch.
- Ghi lại quyết định kiến trúc kèm giới hạn của bằng chứng và cách kiểm chứng bằng các thay đổi tiếp theo.

**Lưu ý cốt lõi:** thay đổi cùng nhau là *tín hiệu để điều tra*, không phải quy tắc máy móc rằng hai class/package luôn phải nằm trong cùng microservice.

## 2. Ba khái niệm cần phân biệt

### 2.1. Cohesion: phần bên trong có cùng lý do thay đổi

Một module có gắn kết tốt khi các phần bên trong phục vụ một năng lực nghiệp vụ rõ ràng và thường thay đổi vì cùng nhóm yêu cầu. Ví dụ, kiểm tra tồn kho, đặt giữ hàng và giải phóng giữ hàng có thể thuộc cùng một năng lực quản lý tồn kho nếu chúng cùng bảo vệ một bất biến nghiệp vụ.

Cohesion không có nghĩa mọi file luôn phải sửa đồng thời. Điều quan trọng là **một ranh giới có trách nhiệm rõ, các quy tắc và dữ liệu sở hữu phù hợp, thay đổi liên quan tập trung vào đó**.

### 2.2. Coupling: phần bên ngoài bị kéo theo thay đổi

Hai module gắn chặt có thể khiến một thay đổi ở A buộc B phải sửa, chạy kiểm thử hoặc triển khai cùng. Ví dụ, sửa cấu trúc dữ liệu Payment có thể làm Checkout phải sửa vì hai phần sử dụng trực tiếp cùng mô hình lưu trữ.

Coupling có nhiều dạng:

| Loại phụ thuộc | Dấu hiệu | Điều cần xác minh |
|---|---|---|
| Nghiệp vụ | Hai quy tắc thường thay đổi cùng một yêu cầu | Chúng thuộc cùng bất biến hay hai năng lực khác nhau? |
| Dữ liệu | Nhiều module sửa chung bảng, entity hoặc transaction | Ai phải là chủ dữ liệu? Có thể truy cập qua hợp đồng rõ ràng không? |
| Mã nguồn | Đổi class/interface chung kéo theo nhiều call site | Contract có ổn định? Có đang chia sẻ model nội bộ quá mức? |
| Runtime | Một luồng đồng bộ cần nhiều thành phần luôn khả dụng | Độ trễ, timeout, lỗi dây chuyền và yêu cầu nhất quán thế nào? |
| Triển khai | Mỗi thay đổi buộc phát hành nhiều phần cùng lúc | Do ranh giới nghiệp vụ hay do pipeline/release chung? |
| Tổ chức | Một PR phải chờ nhiều nhóm sửa và duyệt | Ownership và cách phối hợp có đang tạo nút thắt? |

### 2.3. Co-change: bằng chứng quan sát được

Nếu A và B nằm trong cùng những thay đổi nhiều lần, lịch sử cho thấy **tương quan sửa đổi**. Đây chưa phải bằng chứng A gây thay đổi B, hay cả hai nên gộp chung. Một đợt đổi version thư viện hoặc format toàn repository cũng có thể tạo tương quan giả.

Có thể xem ba lớp chứng cứ bổ sung cho nhau:

1. **Lịch sử thay đổi:** commit, PR, issue; mô-đun nào cùng bị sửa?
2. **Ý nghĩa thay đổi:** quy tắc nghiệp vụ, transaction, model, giao diện nào khiến chúng cùng bị sửa?
3. **Hệ quả vận hành:** có phải cùng kiểm thử, cùng triển khai, đồng bộ dữ liệu hoặc xử lý lỗi không?

## 3. Chọn đơn vị và phạm vi phân tích

Trước khi tính toán, quy định rõ dữ liệu được đếm.

**Đơn vị thay đổi** có thể là:

- **Commit:** dễ lấy từ Git, nhưng phụ thuộc cách commit. Một tính năng có thể trải qua nhiều commit; squash merge có thể gom nhiều sửa đổi thành một.
- **Pull request / merge request:** thường gần với một thay đổi được review và triển khai hơn; một PR lớn vẫn có thể chứa nhiều nhu cầu riêng.
- **Issue, ticket hoặc user story:** gần nguyên nhân nghiệp vụ; cần liên kết đáng tin cậy từ PR/commit đến ticket.
- **Đợt phát hành:** hữu ích khi nghiên cứu phụ thuộc triển khai, nhưng quá rộng để suy ra cohesion ở mức mã nguồn.

Chọn một định nghĩa nhất quán. Với repository có quy trình PR tốt, **một PR hoàn chỉnh** thường là đơn vị phù hợp để nghiên cứu thay đổi nghiệp vụ; commit vẫn hữu ích khi không có metadata PR.

**Đơn vị thành phần** nên bắt đầu ở cấp module/package/feature hoặc bounded context dự kiến. Nếu bắt đầu ở từng file, số cặp rất lớn và các chỉnh sửa nhỏ tạo nhiễu. Có thể drill-down xuống class/file sau khi phát hiện cặp module đáng chú ý.

**Cửa sổ dữ liệu** nên bao phủ vài chu kỳ phát hành thực tế, đủ cả sửa lỗi và phát triển tính năng. Ví dụ: 3–6 tháng đầu để khảo sát, rồi so sánh với giai đoạn gần đây. Khoảng thời gian này chỉ là gợi ý; hệ thống ít thay đổi có thể cần lâu hơn.

Lưu lại: nhánh được phân tích, thời điểm bắt đầu/kết thúc, loại thay đổi được tính, số lượng PR hợp lệ, quy tắc nhóm file thành module, commit squash/cherry-pick và các trường hợp loại bỏ.

## 4. Chuẩn bị lịch sử thay đổi

### 4.1. Thu thập dữ liệu từ nguồn kiểm chứng được

Có thể xem danh sách commit và file sửa đổi bằng Git:

```bash
git log --since="2026-01-01" --until="2026-06-30" \
  --format="COMMIT:%H %ad %s" --date=short --name-only
```

Các mốc ngày là ví dụ; dùng thời kỳ thực tế của repository. Dòng commit đánh dấu một change ID; các đường dẫn tiếp theo là file được sửa trong commit đó.

Để phân tích PR, xuất danh sách file thay đổi từ hệ thống quản lý PR kèm PR ID và liên kết đến issue; có thể lấy dữ liệu qua API hoặc công cụ nội bộ được cấp quyền. Giữ định nghĩa đơn vị thay đổi rõ ràng, tránh vô tình đếm một PR và các commit thuộc PR đó như những thay đổi độc lập.

### 4.2. Chuẩn hóa thành phần

Ví dụ về ánh xạ:

```text
src/checkout/**            → Checkout
src/payment/**             → Payment
src/cart/**                → Cart
src/inventory/**           → Inventory
src/reservation/**         → Reservation
```

Việc ánh xạ phải theo cấu trúc **thực tế** của codebase, không suy ra chỉ từ tên lớp. Ghi riêng trường hợp file đã di chuyển, đổi tên, hoặc một package phục vụ nhiều lĩnh vực.

Tạo bảng gồm ít nhất `change_id`, `component`, ngày, đường dẫn và lý do thay đổi khi có thể. Nếu một PR sửa 12 file thuộc Checkout, ở cấp thành phần Checkout vẫn chỉ được tính **một lần trong PR đó**.

### 4.3. Kiểm soát nhiễu

Các loại thay đổi dễ tạo co-change giả:

- Format toàn dự án, thay license header, rename hàng loạt.
- Nâng phiên bản dependency, đổi cấu hình build hoặc generator.
- Di chuyển file, tái cấu trúc package mà nghiệp vụ không đổi.
- File được sinh tự động, bản build, lockfile hoặc snapshot test bị cập nhật hàng loạt.
- Một PR quá lớn chứa nhiều yêu cầu khác nhau.
- Thay đổi xuyên module vì quy trình release chung chứ không vì mã nghiệp vụ.

Không nên mặc định loại mọi thay đổi cấu hình, test hay shared library: đôi khi chúng phản ánh coupling thực sự. Hãy **gắn nhãn nguyên nhân**, báo cáo hai góc nhìn (toàn bộ và chỉ thay đổi nghiệp vụ), rồi giải thích chênh lệch.

## 5. Đo mức thay đổi đồng thời

Giả sử cửa sổ quan sát có **N** thay đổi hợp lệ. Ký hiệu:

- `n(A)`: số thay đổi có chạm thành phần A.
- `n(B)`: số thay đổi có chạm thành phần B.
- `n(A,B)`: số thay đổi cùng chạm cả A và B.

### 5.1. Số lần thay đổi chung

```text
CoChangeCount(A,B) = n(A,B)
```

Chỉ số này trực quan nhưng thiên về thành phần được sửa thường xuyên. Cặp có 20 lần đổi chung chưa chắc gắn kết hơn cặp có 8/9 lần đổi chung.

### 5.2. Jaccard similarity (đối xứng)

```text
J(A,B) = n(A,B) / (n(A) + n(B) - n(A,B))
```

Giá trị trong khoảng **0–1**, với mẫu số dương. Điểm càng cao cho thấy tỷ lệ phần thay đổi chung trong hợp của hai tập thay đổi càng lớn. Với hai thành phần chưa có thay đổi nào, Jaccard không có cơ sở và nên ghi “không đủ dữ liệu”, không gán 0 một cách tùy tiện.

### 5.3. Tỷ lệ thay đổi kèm theo (có hướng)

```text
P(B thay đổi | A thay đổi) = n(A,B) / n(A)
P(A thay đổi | B thay đổi) = n(A,B) / n(B)
```

Hai tỷ lệ có thể khác nhau. Ví dụ, hầu hết thay đổi ở Payment đều kéo theo Checkout, nhưng nhiều thay đổi Checkout không liên quan Payment. Bất đối xứng này đáng điều tra: có thể Payment phụ thuộc một mô hình Checkout, hoặc chỉ là do phân bố tính năng.

### 5.4. Không kết luận từ mẫu quá nhỏ

Jaccard = 1 khi một cặp cùng xuất hiện trong đúng **một** PR không mạnh bằng Jaccard = 0,8 qua hàng chục PR độc lập. Báo cáo **cả số lần xuất hiện, số lần thay đổi riêng và điểm chuẩn hóa**. Có thể đặt ngưỡng lọc ban đầu như `n(A,B) >= 3` để lập danh sách khảo sát; đây là ngưỡng nghiên cứu tùy bối cảnh, không phải tiêu chuẩn kiến trúc.

Nếu tần suất thay đổi khác biệt lớn giữa các thành phần, có thể phân tích thêm lift hoặc so sánh theo từng giai đoạn, nhưng vẫn cần xem PR cụ thể để tìm nguyên nhân.

## 6. Ví dụ có số liệu

Một hệ thống bán hàng có năm thành phần: **Checkout, Payment, Cart, Inventory, Reservation**. Bảng CSV giả định sau biểu diễn 14 thay đổi; mỗi dòng là một thành phần được chạm trong một thay đổi:

```csv
change_id,component
1,Checkout
1,Payment
2,Checkout
2,Payment
3,Checkout
3,Payment
4,Checkout
4,Cart
5,Checkout
5,Cart
6,Inventory
7,Inventory
7,Reservation
8,Inventory
8,Reservation
9,Inventory
9,Reservation
10,Checkout
11,Payment
12,Cart
13,Checkout
13,Payment
14,Inventory
14,Reservation
```

Đặt dữ liệu vào file `changes.csv`. Đo các cặp thành phần bằng Python thuần thư viện chuẩn:

```python
import csv
from collections import Counter, defaultdict
from itertools import combinations

changes = defaultdict(set)

with open("changes.csv", encoding="utf-8", newline="") as stream:
    for row in csv.DictReader(stream):
        change_id = row["change_id"].strip()
        component = row["component"].strip()
        if change_id and component:
            changes[change_id].add(component)

single = Counter()
joint = Counter()

for components in changes.values():
    for component in components:
        single[component] += 1
    for pair in combinations(sorted(components), 2):
        joint[pair] += 1

for (a, b), together in sorted(
    joint.items(), key=lambda item: (-item[1], item[0])
):
    union = single[a] + single[b] - together
    jaccard = together / union
    b_given_a = together / single[a]
    a_given_b = together / single[b]
    print(
        f"{a} + {b}: count={together}, "
        f"J={jaccard:.2f}, "
        f"P({b}|{a})={b_given_a:.0%}, "
        f"P({a}|{b})={a_given_b:.0%}"
    )
```

Mỗi thành phần chỉ được đếm một lần trên một `change_id`, dù thay đổi đó sửa nhiều file trong thành phần ấy. Đoạn mã tính trên dữ liệu **đã chuẩn hóa**, không tự xác định lý do hoặc mức quan trọng của từng PR.

Kết quả:

| Cặp thành phần | n(A) | n(B) | Cùng thay đổi | Jaccard | Diễn giải ban đầu |
|---|---:|---:|---:|---:|---|
| Inventory – Reservation | 5 | 4 | 4 | 0,80 | Tương quan cao; cần xem bất biến tồn kho/giữ chỗ |
| Checkout – Payment | 7 | 5 | 4 | 0,50 | Có quan hệ đáng chú ý; Payment thay đổi kèm Checkout ở 4/5 lần |
| Checkout – Cart | 7 | 3 | 2 | 0,25 | Liên hệ hiện diện nhưng yếu hơn hai cặp trên |

Số liệu chỉ là **minh họa**, không được dùng làm kết quả thật của một dự án.

### Đọc đúng kết quả

- **Inventory – Reservation:** 4/4 thay đổi của Reservation đi kèm Inventory. Có thể cả hai bảo vệ vòng đời giữ hàng, hoặc hai phần đang dùng chung dữ liệu cần đồng bộ. Cần mở từng PR để xác định.
- **Checkout – Payment:** 4/5 thay đổi Payment đi kèm Checkout, nhưng chỉ 4/7 thay đổi Checkout đi kèm Payment. Có thể ranh giới hợp đồng chưa ổn định, cũng có thể tính năng thanh toán thật sự thay đổi ở cả hai luồng.
- **Checkout – Cart:** hai lần cùng sửa chưa đủ để bắt buộc gộp thành một dịch vụ.

Nếu một PR duy nhất cập nhật cả năm thành phần vì nâng cấp framework, sau khi lọc nhiễu, thứ tự các cặp có thể thay đổi đáng kể. Vì vậy, **ma trận chỉ là bước ưu tiên điều tra**, không phải bản đồ bounded context đã được xác nhận.

## 7. Từ cặp thay đổi chung đến cụm gắn kết

Có thể xây dựng một **đồ thị thành phần**:

- **Nút:** module, package hoặc năng lực nghiệp vụ.
- **Cạnh:** hai nút xuất hiện cùng trong các thay đổi.
- **Trọng số cạnh:** Jaccard hoặc một thước đo có chuẩn hóa, đặt cạnh số lần thay đổi thực tế.
- **Thời gian:** so sánh trọng số theo từng cửa sổ để phân biệt quan hệ lâu dài với chiến dịch ngắn hạn.

Ví dụ minh họa từ bảng trên:

```text
  Inventory ========= Reservation      J = 0,80
  Checkout  =====     Payment          J = 0,50
  Checkout  ==        Cart             J = 0,25
```

Một cụm có nhiều cạnh nội bộ mạnh và ít cạnh mạnh ra ngoài là **ứng viên** có cohesion tốt. Tuy nhiên, phân cụm tự động có thể gom hai bounded context khác nhau vì chúng đang chia sẻ model hoặc release pipeline không phù hợp. Hãy dùng cụm làm đầu vào cho workshop với nhóm nghiệp vụ, kiến trúc và người duy trì mã.

Khi số thành phần lớn, có thể tạo heatmap ma trận Jaccard và đồ thị, nhưng giữ nhãn số lần thay đổi chung để tránh các điểm cao do mẫu ít.

## 8. Xác định vì sao các thành phần thay đổi cùng nhau

Với mỗi cặp quan trọng, chọn một số PR đại diện ở nhiều thời điểm, xem issue, diff và kiểm thử kèm theo. Phân loại nguyên nhân:

| Quan sát | Câu hỏi phân tích | Hướng xử lý có thể phù hợp |
|---|---|---|
| Cùng thay đổi một bất biến nghiệp vụ | Quy tắc nào phải đúng trong cùng một transaction? | Xem xét đặt chung một boundary hoặc xác định chủ sở hữu invariant |
| A thay đổi vì DTO của B đổi | DTO này là contract công khai hay model nội bộ? | Cố định contract, tách model nội bộ, versioning khi cần |
| A và B cùng sửa một bảng dữ liệu | Ai thực sự sở hữu bảng và vòng đời dữ liệu? | Thiết kế ownership, API/event, loại truy cập xuyên boundary |
| Cùng thay đổi do một UI feature | Đây là hành trình người dùng xuyên nhiều năng lực riêng biệt? | Có thể giữ các boundary độc lập, điều phối qua application workflow |
| Cùng đổi do một thư viện/build/version | Có yêu cầu nghiệp vụ chung không? | Ghi là tác động hạ tầng, không suy diễn gộp nghiệp vụ |
| Cùng deploy dù code không liên quan | Pipeline hay runtime có buộc phát hành chung? | Cải thiện CI/CD, test và cách đóng gói trước khi phân rã |
| Cùng sửa vì thiếu tests hoặc mocks | Tương tác thật có cần đồng bộ đến mức ấy? | Bổ sung contract test, giảm phụ thuộc build/test |
| Cùng sửa do schema hoặc giao thức thay đổi | Mức tương thích ngược có thể cải thiện không? | Thêm chính sách tiến hóa hợp đồng, migration nhiều bước |

Điều quan trọng không phải tìm ra “cặp cao nhất” mà là xác định **lý do thay đổi có ổn định và có ý nghĩa đối với ranh giới sở hữu hay không**.

## 9. Dùng kết quả khi thiết kế ranh giới microservice

### Bước 1: Xác định năng lực nghiệp vụ

Vẽ các bounded context dự kiến bằng domain language, actor, sự kiện và quy tắc. Chỉ sau đó mới đối chiếu lịch sử co-change để kiểm tra giả thuyết về ranh giới. Package có tên giống nhau không đủ để coi là cùng domain.

### Bước 2: Kiểm tra các bất biến và giao dịch

Ví dụ, nếu Inventory và Reservation phải cập nhật atomically để không bán vượt tồn kho, một boundary sở hữu cả bất biến đó có thể giảm rủi ro. Nhưng nếu Reservation chỉ là quy trình đặt chỗ có vòng đời riêng và chấp nhận nhất quán cuối cùng, có thể cân nhắc giao tiếp sự kiện cùng cơ chế bù trừ phù hợp.

Đừng dùng co-change để bỏ qua các yêu cầu về nhất quán, idempotency, retry, timeout hay đối soát.

### Bước 3: Đánh giá thay đổi xuyên ranh giới

Với từng ranh giới ứng viên, hỏi:

- Một tính năng bình thường cần sửa bao nhiêu module/dịch vụ?
- Bao nhiêu thay đổi cần chỉnh contract giữa hai dịch vụ?
- Có phải phối hợp triển khai cùng lúc hoặc sửa dữ liệu của nhau không?
- Một nhóm có thể chịu trách nhiệm end-to-end cho năng lực của họ không?
- Số lần gọi đồng bộ và đường đi lỗi có làm giảm độ tin cậy hay tăng độ trễ không?

Một ranh giới tốt thường giúp **thay đổi phổ biến nằm gọn trong một năng lực** và làm cho tương tác cần thiết trở nên rõ ràng qua hợp đồng.

### Bước 4: So sánh phương án với chi phí

| Phương án | Lợi ích có thể có | Rủi ro cần đo |
|---|---|---|
| Giữ chung trong monolith nhưng cải thiện module | Ít chi phí phân tán, có thể tăng cohesion | Vẫn chung quy trình triển khai nếu không thay đổi pipeline |
| Giữ các phần co-change cao trong cùng bounded context | Giảm nhu cầu sửa contract xuyên ranh giới | Boundary có thể lớn nếu không kiểm tra nghiệp vụ |
| Tách phần độc lập thành dịch vụ | Deploy/scale/ownership độc lập khi có nhu cầu thật | Network, observability, dữ liệu và vận hành phức tạp hơn |
| Tách cặp co-change cao thành hai dịch vụ | Có thể phù hợp nếu business contexts thật sự riêng | Nguy cơ phải phối hợp thay đổi, cập nhật version và transaction phân tán |

Nếu dữ liệu và phân tích nghiệp vụ chưa đủ rõ, **modular monolith với boundary được kiểm tra bằng quy tắc phụ thuộc** là bước học hỏi hữu ích trước khi đầu tư vào microservices.

### Bước 5: Kiểm chứng bằng thay đổi thực tế

Thử một hoặc hai tính năng đại diện với ranh giới dự kiến. Ghi số module phải sửa, số contract phải cập nhật, thời gian review/triển khai, tỷ lệ thay đổi phải phối hợp giữa nhóm và lỗi phát sinh. So sánh với baseline trên cùng loại công việc; tránh suy diễn cải thiện chỉ vì cấu trúc package trông đẹp hơn.

## 10. Các sai lầm thường gặp

**Lấy số commit làm “độ gắn kết” tuyệt đối.** Thành phần thay đổi nhiều thường có count lớn. Dùng count cùng Jaccard, tỷ lệ có hướng và ngưỡng dữ liệu tối thiểu.

**Gộp theo cạnh mạnh mà không đọc diff.** Một dependency cập nhật hàng loạt có thể tạo kết quả giả. Kiểm tra nguyên nhân trên các PR đại diện.

**Dùng lịch sử ngắn hoặc dữ liệu chưa hoàn chỉnh.** Vài PR không đủ chứng minh quan hệ dài hạn; thiếu ticket, squash commit hoặc đổi tên file có thể làm sai số.

**Xem chung một PR là chung một trách nhiệm.** Một PR liên quan UI, API, database và logging có thể mô tả một lát cắt theo chức năng qua nhiều bounded context.

**Bỏ qua sự lệch hướng của tỷ lệ có điều kiện.** `P(B|A)` cao không đồng nghĩa `P(A|B)` cao; xem cả hai để nhận diện chiều ảnh hưởng.

**Cho rằng “ít đổi chung” nghĩa là độc lập khi chạy.** Hai phần hiếm sửa cùng nhau vẫn có thể phụ thuộc runtime cực mạnh hoặc dùng chung một database không thể tách transaction.

**Tách dịch vụ ngay sau phân tích.** Phân rã service còn phụ thuộc ownership, mức tải, khả năng triển khai độc lập, giám sát, dữ liệu, bảo mật và chi phí. Co-change cung cấp một góc nhìn để cân nhắc, không thay thế kiến trúc tổng thể.

## 11. Mẫu ghi nhận kết quả phân tích

```markdown
# Co-change analysis: <tên hệ thống / thời kỳ>

Mục tiêu phân tích:
Nguồn dữ liệu: <repo, nhánh, PR/commit/issue>
Đơn vị thay đổi: <PR hoặc commit hoặc ticket>
Đơn vị thành phần: <module/package/bounded context>
Khoảng quan sát:
Số thay đổi hợp lệ:
Quy tắc ánh xạ file → thành phần:
Quy tắc lọc / gắn nhãn thay đổi hàng loạt:

Các cặp nổi bật:
| A | B | n(A) | n(B) | n(A,B) | Jaccard | P(B|A) | P(A|B) |

PR/issue đại diện và nguyên nhân thay đổi chung:
- ...

Ranh giới nghiệp vụ và bất biến liên quan:
Phụ thuộc dữ liệu / runtime / triển khai cần kiểm tra:
Các phương án kiến trúc được cân nhắc:
Quyết định hoặc giả thuyết cần thử:
Tiêu chí đánh giá sau thử nghiệm:
Giới hạn và yếu tố gây nhiễu:
Người chịu trách nhiệm / ngày xem xét lại:
```

Hãy giữ đường dẫn đến PR/issue/diff và công thức tính để lần phân tích tiếp theo có thể tái lập trên một khoảng thời gian mới.

## 12. Bài tập thực hành

Một đội phát hiện qua sáu tháng rằng **Pricing** và **Promotion** được sửa cùng nhau trong 15 PR; Pricing xuất hiện trong 20 PR, Promotion trong 18 PR. Trong khi đó, **Pricing** và **Catalog** cùng sửa trong 6 PR; Catalog xuất hiện trong 25 PR.

1. Tính Jaccard cho hai cặp. Cặp nào có dấu hiệu gắn kết cao hơn?
2. Tính `P(Promotion|Pricing)` và `P(Pricing|Promotion)`; giải thích sự khác nhau.
3. Nêu ít nhất ba loại PR có thể làm tăng co-change nhưng không chứng minh hai phần có cùng nghiệp vụ.
4. Đặt năm câu hỏi về bất biến, quyền sở hữu dữ liệu và quy trình phát hành trước khi quyết định boundary.
5. Đề xuất một thử nghiệm nhỏ để giảm thay đổi xuyên boundary và một chỉ số để kiểm chứng hiệu quả.

Gợi ý đối chiếu phép tính:

- Pricing – Promotion: `15 / (20 + 18 - 15) = 15/23 ≈ 0,652`.
- Pricing – Catalog: `6 / (20 + 25 - 6) = 6/39 ≈ 0,154`.
- `P(Promotion|Pricing) = 15/20 = 75%`; `P(Pricing|Promotion) = 15/18 ≈ 83,3%`.

Cặp Pricing – Promotion đáng điều tra trước, nhưng kết luận về gộp/tách vẫn phụ thuộc ý nghĩa của các PR và ranh giới nghiệp vụ.

## 13. Ghi nhớ

Phân tích thay đổi đồng thời biến lịch sử sửa mã thành **bằng chứng định lượng về nơi các thay đổi có xu hướng đi cùng nhau**. Hãy thu thập dữ liệu theo đơn vị thống nhất, chuẩn hóa thành phần, loại nhiễu có giải thích, tính cả count và tỷ lệ, rồi đọc các PR thực tế để xác định nguyên nhân. Ranh giới microservice tốt cần phù hợp với **năng lực nghiệp vụ, dữ liệu sở hữu, bất biến giao dịch và khả năng thay đổi độc lập**; co-change giúp kiểm tra và cải thiện giả thuyết đó.
