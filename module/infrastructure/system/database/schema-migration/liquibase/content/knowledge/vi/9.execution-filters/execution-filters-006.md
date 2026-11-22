# Hành vi khi không truyền bộ lọc hoặc changeset không có nhãn

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, thuộc chương **Bộ lọc thực thi**, một câu hỏi rất dễ gây sai sót khi triển khai là: **Nếu không truyền context hoặc label filter khi chạy Liquibase, những changeset nào sẽ được thực thi?** Một câu hỏi liên quan là: **Khi pipeline có truyền bộ lọc, changeset không gắn context hoặc label có bị bỏ qua hay không?**

Câu trả lời có ý nghĩa vận hành quan trọng: theo cơ chế lọc thông thường của Liquibase, **không truyền bộ lọc không có nghĩa là “không chạy changeset nào”**; và **changeset không có nhãn không bị loại chỉ vì người chạy đã truyền một label filter**. Bộ lọc giúp chọn các changeset có điều kiện phù hợp, còn changeset không mang điều kiện lọc tương ứng thường được xem là áp dụng chung. Riêng cú pháp yêu cầu context tường minh bằng tiền tố **@** tạo ra một ngoại lệ cần hiểu kỹ.

Bài học giúp xác định chính xác hành vi mặc định, đọc và thiết kế changelog có context/label, kiểm tra các tình huống thiếu hoặc không khớp bộ lọc, và vận hành migration có kiểm chứng qua Liquibase CLI, Spring Boot và CI/CD. Đây là một phần của mục tiêu lớn hơn: quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum, lịch sử triển khai và rollback an toàn qua nhiều môi trường.

## 1. Bộ lọc thực thi giải quyết vấn đề gì?

Một changelog có thể chứa cả thay đổi dùng chung và thay đổi chỉ phù hợp với một tập môi trường hoặc một đợt triển khai. Ví dụ:

- Tạo bảng **customer_event** cho mọi môi trường.
- Chèn một số dữ liệu minh họa cho môi trường phát triển.
- Tạo dữ liệu chỉ phục vụ kiểm thử tích hợp.
- Kích hoạt một thay đổi thuộc đợt phát hành **release-2026**.
- Chạy một thao tác chỉ khi đồng thời đáp ứng điều kiện môi trường và điều kiện phát hành.

Liquibase cung cấp hai cơ chế lựa chọn thường gặp:

- **Context**: thuộc tính **contextFilter** trên changeset thể hiện điều kiện lựa chọn theo context; bên thực thi truyền **context filter** tương ứng. Trong ví dụ, context có thể là **dev**, **test** hoặc **prod**.
- **Label**: thuộc tính **labels** gắn nhãn phân loại cho changeset; bên thực thi truyền **label filter** để chọn tập nhãn cần áp dụng. Trong ví dụ, nhãn có thể là **release-2026**, **feature-billing** hoặc **hotfix**.

Context và label là hai trục khác nhau. Một changeset có thể không mang trục nào, mang một trục hoặc mang cả hai. Tên context/label do nhóm thiết kế; Liquibase không tự hiểu rằng từ **dev** là an toàn hoặc từ **prod** là dữ liệu thật. Cơ chế hoạt động phụ thuộc **thuộc tính trong changelog, bộ lọc được truyền khi chạy và phiên bản Liquibase thực tế**.

Bộ lọc cũng không quyết định một mình việc changeset có chạy hay không. Liquibase còn kiểm tra định danh changeset, bảng **DATABASECHANGELOG**, trạng thái đã triển khai, các thuộc tính như **runAlways/runOnChange**, **dbms**, precondition và khả năng thực thi trên database. Vì vậy, trong bài này, từ **“đủ điều kiện”** nghĩa là **đã vượt qua riêng khâu lựa chọn bằng context/label**; việc thật sự thực thi còn tùy các cơ chế khác.

## 2. Mặc định quan trọng nhất: không truyền filter thì điều gì xảy ra?

Khi thực hiện một lệnh cập nhật bình thường mà **không truyền context filter và không truyền label filter**, Liquibase không mặc định loại các changeset chỉ vì chúng được gắn context hoặc label.

Cụ thể:

1. **Changeset không có context, không có label**: đủ điều kiện lọc để chạy.
2. **Changeset có context thông thường**, chẳng hạn **dev**: vẫn đủ điều kiện khi hoàn toàn không truyền context filter.
3. **Changeset có label**, chẳng hạn **release-2026**: vẫn đủ điều kiện khi không truyền label filter.
4. **Changeset có cả context thông thường và label**: vẫn đủ điều kiện nếu cả hai bộ lọc đều không được truyền.
5. **Changeset yêu cầu context tường minh bằng tiền tố @**, chẳng hạn **@dev**: không đủ điều kiện nếu không truyền context filter phù hợp.

Đây là điểm khác biệt giữa “gắn context thông thường” và “yêu cầu người chạy chỉ định context”. Nếu chỉ thêm **contextFilter: dev** vào một changeset chứa dữ liệu phát triển rồi chạy **liquibase update** không có bộ lọc context, changeset đó vẫn có thể chạy trong production. Nếu sự an toàn của dữ liệu phụ thuộc vào việc chỉ chạy khi người triển khai chọn **dev**, có thể dùng cú pháp **@dev** ở phạm vi được phiên bản Liquibase hỗ trợ, kết hợp với cấu hình pipeline và các biện pháp kiểm soát khác.

**Không truyền filter không đồng nghĩa với filter rỗng có ý nghĩa chặn tất cả.** Trong vận hành, hãy kiểm tra giá trị thực sự được truyền từ CLI, cấu hình ứng dụng hoặc biến môi trường; thiếu cấu hình thường dẫn tới phạm vi rộng hơn dự kiến, chứ không tự động áp dụng chính sách từ chối.

## 3. Changeset không có nhãn được xử lý thế nào?

Giả sử một changeset **không khai báo labels**. Khi người triển khai chạy với một label filter bất kỳ, changeset đó **vẫn đủ điều kiện lọc bằng label**. Nó được xem là changeset áp dụng chung, không yêu cầu phải khớp một nhãn cụ thể.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "001-create-customer-event"
      author: "platform"
      changes:
        - createTable:
            tableName: customer_event
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false

  - changeSet:
      id: "002-add-release-column"
      author: "platform"
      labels: "release-2026"
      changes:
        - addColumn:
            tableName: customer_event
            columns:
              - column:
                  name: source
                  type: VARCHAR(40)
~~~

Nếu chỉ xét label:

| Lệnh/chế độ lọc | Changeset 001, không nhãn | Changeset 002, nhãn release-2026 |
|---|---|---|
| Không truyền label filter | Đủ điều kiện | Đủ điều kiện |
| Label filter là **release-2026** | Đủ điều kiện | Đủ điều kiện |
| Label filter là **hotfix** | Đủ điều kiện | Không khớp |
| Label filter là **!release-2026** | Đủ điều kiện | Không khớp |

Bảng chỉ nói về **label matching**, giả định không có context, dbms hoặc precondition chặn thực thi và changeset chưa từng được ghi nhận. Việc một changeset không có nhãn vẫn đủ điều kiện **không có nghĩa bộ lọc bị vô hiệu hóa**: label filter vẫn kiểm tra các changeset có nhãn, nhưng không biến các changeset áp dụng chung thành changeset bị từ chối.

Nếu mục tiêu là chạy **duy nhất** một nhóm thay đổi được gắn nhãn và tuyệt đối không chạy changeset không nhãn, **label filter đơn thuần không đáp ứng yêu cầu đó**. Cần thiết kế phạm vi changelog hoặc pipeline phù hợp, hoặc điều kiện lựa chọn bổ sung có thể kiểm chứng. Đừng suy ra rằng label filter giống phép lọc SQL chỉ lấy hàng có nhãn tương ứng.

## 4. Context thông thường và context yêu cầu tường minh bằng @

Đối với context, có một ngoại lệ đặc biệt: tiền tố **@** dùng để yêu cầu phải có context được chỉ định khi thực thi.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "010-dev-seed-normal"
      author: "platform"
      contextFilter: "dev"
      changes:
        - sql:
            sql: "INSERT INTO customer_event (id) VALUES (10)"

  - changeSet:
      id: "011-dev-seed-explicit"
      author: "platform"
      contextFilter: "@dev"
      changes:
        - sql:
            sql: "INSERT INTO customer_event (id) VALUES (11)"
~~~

Trong ví dụ này, hai changeset đều có ý định liên quan đến **dev**. Tuy nhiên:

| Context filter lúc chạy | 010: contextFilter=dev | 011: contextFilter=@dev |
|---|---|---|
| Không truyền | Đủ điều kiện | Không đủ điều kiện |
| **dev** | Đủ điều kiện | Đủ điều kiện |
| **prod** | Không khớp | Không khớp |

Khác biệt này rất quan trọng nếu cùng changelog được triển khai bằng công cụ CLI, ứng dụng Spring Boot và pipeline có cấu hình không hoàn toàn giống nhau. **@** chỉ là cơ chế của biểu thức context theo cú pháp mà Liquibase hỗ trợ; không được suy diễn rằng cứ thêm **@** vào một label là tạo ra hành vi y hệt.

Để tránh phụ thuộc vào mẹo cú pháp không được phiên bản dự án hỗ trợ, cần xác nhận **contextFilter**, tiền tố **@** và cách ghi thuộc tính trong đúng loại changelog/phiên bản Liquibase đang dùng. Khi làm việc với phiên bản cũ, tên thuộc tính và tùy chọn CLI có thể khác. Các kết luận vận hành phải được kiểm chứng bằng runtime thật.

## 5. Khi chỉ truyền một trong hai bộ lọc

Một lỗi thiết kế phổ biến là cho rằng cứ truyền một bộ lọc bất kỳ thì tất cả changeset đều chịu một lớp bảo vệ chung. Thực tế context và label được xét riêng.

### 5.1. Có context filter, không có label filter

Giả sử lệnh update truyền **context-filter=prod**, còn label filter bị bỏ trống:

- Changeset **không gắn context** vẫn đủ điều kiện ở lớp context.
- Changeset có context **prod** đủ điều kiện.
- Changeset chỉ có context **dev** không khớp.
- Changeset có nhãn **release-2026** nhưng **không mang context** vẫn đủ điều kiện: nhãn không tự chặn vì label filter không được truyền.
- Changeset có **@dev** không khớp prod.

Như vậy, **context-filter=prod không có nghĩa là chỉ chạy changeset vừa có context prod vừa có label release dành cho production**.

### 5.2. Có label filter, không có context filter

Nếu pipeline truyền **label-filter=release-2026** nhưng không truyền context filter:

- Changeset không có nhãn vẫn đủ điều kiện ở lớp label.
- Changeset có nhãn **release-2026** đủ điều kiện.
- Changeset chỉ có nhãn **hotfix** không khớp.
- Changeset có context thông thường **dev** nhưng nhãn **release-2026** có thể đủ điều kiện vì không có context filter chặn.
- Changeset có context **@dev** vẫn yêu cầu context tường minh, nên chưa đủ điều kiện.

Vì vậy, label filter không phải lựa chọn thay thế cho context filter khi nhóm đang phân tách môi trường.

### 5.3. Có cả context và label filter

Một changeset có cả contextFilter và labels thường phải thỏa **điều kiện của cả hai trục** khi hai bộ lọc đều được truyền. Changeset không gắn một trục thì không bị chặn bởi chính trục trống đó.

Có thể hình dung:

~~~text
                    Changeset chưa chạy
                            |
                            v
               Kiểm tra context eligibility
                   |                 |
                 Đạt              Không đạt
                   |                 |
                   v                 v
               Kiểm tra label     Bỏ qua
                   |
              +----+----+
              |         |
             Đạt     Không đạt
              |         |
              v         v
       Tiếp tục xét   Bỏ qua
       lịch sử, dbms,
       precondition...
~~~

Mô hình trên giải thích **lựa chọn theo bộ lọc**, không mô tả toàn bộ thứ tự nội bộ mà Liquibase thực hiện tại runtime. Bảng DATABASECHANGELOG và các quy tắc execution còn quyết định phần triển khai thực tế.

## 6. Bảng chân trị tổng hợp cho một changelog minh họa

Xét sáu changeset dưới đây, giả định chúng đều chưa được triển khai, hợp lệ trên DBMS đích, không có precondition chặn và không thuộc trường hợp chạy lại đặc biệt:

| ID | Context trong changeset | Labels | Ý nghĩa |
|---|---|---|---|
| **A** | Không khai báo | Không khai báo | Schema dùng chung |
| **B** | **dev** | Không khai báo | Dữ liệu dev theo context thông thường |
| **C** | **@dev** | Không khai báo | Dữ liệu yêu cầu chỉ định dev tường minh |
| **D** | Không khai báo | **release-2026** | Thay đổi gắn đợt phát hành |
| **E** | **@dev** | **release-2026** | Cần dev tường minh và nhãn phát hành phù hợp |
| **F** | Không khai báo | Không khai báo | Thay đổi dùng chung bổ sung |

Kết quả xét riêng context/label:

| Filter truyền khi update | A | B | C | D | E | F |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Không context, không label filter | ✓ | ✓ | – | ✓ | – | ✓ |
| Context **prod**, không label filter | ✓ | – | – | ✓ | – | ✓ |
| Context **dev**, không label filter | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Không context, label **release-2026** | ✓ | ✓ | – | ✓ | – | ✓ |
| Context **dev**, label **release-2026** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Context **dev**, label **hotfix** | ✓ | ✓ | ✓ | – | – | ✓ |
| Context **prod**, label **release-2026** | ✓ | – | – | ✓ | – | ✓ |

**✓** nghĩa là đủ điều kiện qua cả hai bộ lọc, **–** nghĩa là bị loại ở lớp lọc. Đặc biệt:

- A và F **không có nhãn hoặc context** nhưng vẫn đủ điều kiện trong mọi hàng.
- B có context **dev** nhưng vẫn đủ điều kiện khi không truyền context filter.
- D có label **release-2026** nhưng vẫn đủ điều kiện khi không truyền label filter.
- C và E **không chạy nếu thiếu context filter phù hợp**, do dùng **@dev**.
- Truyền đồng thời dev và release-2026 **không làm B, C, A hoặc F bị loại chỉ vì chúng không có nhãn**.

Bảng này nên được sử dụng như bài thử nền tảng để review logic lọc. Nếu cần hành vi hạn chế hơn, phải thiết kế lại cách gắn điều kiện, tổ chức changelog hoặc cấu hình triển khai.

## 7. Ví dụ YAML tự chứa để quan sát hành vi

Dưới đây là một changelog minh họa có cả changeset dùng chung, có context thông thường, có context bắt buộc tường minh và có labels. Dùng **trên database thử nghiệm riêng**; mỗi lần muốn so sánh hai tình huống, cần bắt đầu từ trạng thái giống nhau hoặc khôi phục môi trường, vì changeset đã chạy được ghi vào DATABASECHANGELOG và sẽ không tự chạy lại.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "filter-demo-001-create-table"
      author: "platform"
      changes:
        - createTable:
            tableName: filter_demo
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: note
                  type: VARCHAR(80)
                  constraints:
                    nullable: false

  - changeSet:
      id: "filter-demo-002-normal-dev"
      author: "platform"
      contextFilter: "dev"
      changes:
        - insert:
            tableName: filter_demo
            columns:
              - column:
                  name: id
                  valueNumeric: 2
              - column:
                  name: note
                  value: "normal-dev"

  - changeSet:
      id: "filter-demo-003-explicit-dev"
      author: "platform"
      contextFilter: "@dev"
      changes:
        - insert:
            tableName: filter_demo
            columns:
              - column:
                  name: id
                  valueNumeric: 3
              - column:
                  name: note
                  value: "explicit-dev"

  - changeSet:
      id: "filter-demo-004-release"
      author: "platform"
      labels: "release-2026"
      changes:
        - insert:
            tableName: filter_demo
            columns:
              - column:
                  name: id
                  valueNumeric: 4
              - column:
                  name: note
                  value: "release-2026"

  - changeSet:
      id: "filter-demo-005-explicit-dev-release"
      author: "platform"
      contextFilter: "@dev"
      labels: "release-2026"
      changes:
        - insert:
            tableName: filter_demo
            columns:
              - column:
                  name: id
                  valueNumeric: 5
              - column:
                  name: note
                  value: "dev-and-release"

  - changeSet:
      id: "filter-demo-006-common"
      author: "platform"
      changes:
        - insert:
            tableName: filter_demo
            columns:
              - column:
                  name: id
                  valueNumeric: 6
              - column:
                  name: note
                  value: "common"
~~~

Trên một database ban đầu chưa có bảng **filter_demo**, nếu chạy update mà **không cấu hình cả hai bộ lọc**, dữ liệu dự kiến sau update là các dòng có ID **2, 4, 6**; hai dòng **3, 5** bị loại do **@dev**. Bảng được tạo bởi changeset đầu tiên, nhưng chính thao tác tạo bảng không sinh dòng dữ liệu.

Nếu chạy từ một database thử nghiệm mới với context **prod**, dự kiến có các dòng **4, 6**. Nếu chạy với context **dev** và label **hotfix**, dự kiến có các dòng **2, 3, 6**. Những kết quả này minh họa nguyên tắc lọc chứ không phải kết quả đã chạy tại môi trường thực tế.

Ví dụ cho thấy **gắn nhãn không bảo vệ một thay đổi khỏi lần update không có label filter**, và **gắn context thông thường không bảo vệ một thay đổi khỏi lần update không có context filter**.

## 8. Kiểm chứng bằng Liquibase CLI

Khi dùng Liquibase CLI, có thể xem trước kết quả lựa chọn bằng các lệnh phù hợp với phiên bản đang chạy. Cú pháp dưới đây minh họa cách truyền filter ở các phiên bản Liquibase hỗ trợ tên tùy chọn **--context-filter** và **--label-filter**:

~~~bash
liquibase --version

liquibase --changelog-file=filter-demo.yaml update-sql

liquibase --changelog-file=filter-demo.yaml \
  --context-filter=dev update-sql

liquibase --changelog-file=filter-demo.yaml \
  --label-filter=release-2026 update-sql

liquibase --changelog-file=filter-demo.yaml \
  --context-filter=dev \
  --label-filter=release-2026 update-sql
~~~

Dấu **\\** trong đoạn minh họa dùng để xuống dòng theo kiểu shell POSIX; nếu chạy trên PowerShell hoặc CMD, hãy đặt toàn bộ lệnh trên một dòng hoặc dùng cú pháp xuống dòng phù hợp với shell đang dùng. Tên tùy chọn context cũng có khác biệt giữa một số phiên bản CLI, nên cần xác nhận từ **liquibase --help** hoặc tài liệu của đúng phiên bản dự án.

**update-sql** giúp xem SQL Liquibase dự kiến thực hiện. Để so sánh chính xác, mỗi trường hợp cần kết nối tới database thử nghiệm có cùng lịch sử ban đầu. Nếu chạy nhiều lệnh liên tiếp sau khi đã update thành công một lần, những changeset đã nằm trong DATABASECHANGELOG sẽ không xuất hiện như thay đổi mới; đây là hành vi kiểm soát lịch sử, không phải bằng chứng bộ lọc đã loại chúng.

Có thể bổ sung:

~~~bash
liquibase --changelog-file=filter-demo.yaml validate
liquibase --changelog-file=filter-demo.yaml status --verbose
~~~

Khi đánh giá kết quả, cần đối chiếu **ID changeset**, context, label, SQL được sinh và lịch sử đã ghi nhận. Không chỉ đếm tổng số câu SQL: một changeset có thể sinh nhiều câu SQL, và precondition hoặc những đặc tính khác có thể tác động đến nội dung dự kiến.

## 9. Trường hợp đã chạy một phần rồi thay đổi bộ lọc

Giả sử lần đầu chạy pipeline không truyền filter. Một số changeset đã được ghi vào **DATABASECHANGELOG**, nhưng changeset mang **@dev** bị bỏ qua. Lần sau pipeline chạy với context **dev**:

1. Liquibase lại xét danh sách changeset trong changelog.
2. Các changeset đã triển khai thông thường được nhận diện qua định danh lịch sử và không chạy lại, trừ khi có thuộc tính điều khiển thực thi lại như **runAlways** hoặc **runOnChange**.
3. Các changeset từng bị bỏ qua do context giờ có thể đủ điều kiện và được chạy lần đầu.
4. Những changeset được thực thi thành công sẽ được ghi nhận trong DATABASECHANGELOG.

**Bị bỏ qua bởi bộ lọc khác với “đã thực thi”.** Một changeset không được chọn thông thường chưa trở thành bản ghi đã triển khai chỉ vì nó có mặt trong file. Điều này giúp giải thích vì sao một thay đổi “cũ” bất ngờ xuất hiện trong đợt update mới sau khi ai đó sửa bộ lọc của pipeline.

Bảng lịch sử còn có checksum để đối chiếu định nghĩa changeset đã được chạy. Khi bổ sung filter hoặc thay đổi cấu trúc changelog, cần cẩn trọng không chỉnh sửa ngẫu nhiên phần nội dung đã phát hành. **Thay đổi bộ lọc chạy** khác với **thay đổi định nghĩa changeset**; việc thay metadata hoặc nội dung có thể ảnh hưởng checksum tùy thuộc loại thay đổi và phiên bản Liquibase. Đừng dùng **clear-checksums** để che lỗi sai khác chưa được điều tra.

Một cách kiểm tra hữu ích là xem:

~~~sql
SELECT ID, AUTHOR, FILENAME, EXECTYPE, DATEEXECUTED, MD5SUM
FROM DATABASECHANGELOG
ORDER BY ORDEREXECUTED;
~~~

Hãy đối chiếu với changelog và log triển khai. Không được coi việc một ID không xuất hiện trong DATABASECHANGELOG là bằng chứng duy nhất rằng filter đã chặn nó: còn có thể do precondition, cấu hình dbms, thứ tự thực thi hoặc update thất bại trước đó.

## 10. Filter không phải cơ chế bảo mật hay thay thế precondition

Context và label dùng để **lựa chọn** những changeset nên được xem xét trong một lần thực thi. Chúng không xác minh quyền của người triển khai, không khẳng định database đang là dev hay prod, và không tự ngăn một người có quyền kết nối production chạy lệnh thiếu filter.

Các tình huống cần xử lý rõ:

- **Dữ liệu test/dev**: nên tổ chức thành changelog hoặc tập thay đổi được bảo vệ bởi quy trình triển khai, kết hợp điều kiện context tường minh khi thích hợp. Không dựa độc nhất vào một nhãn **dev**.
- **Thay đổi nhạy cảm với môi trường**: cần kiểm soát cấu hình môi trường và quyền database, thêm các kiểm tra thích hợp ở pipeline.
- **Precondition**: dùng để kiểm tra trạng thái thực tế trước khi chạy thay đổi, ví dụ bảng đã tồn tại hoặc dữ liệu đã đáp ứng ràng buộc. Precondition không tự động thay thế logic chọn môi trường.
- **dbms**: dùng để giới hạn theo hệ quản trị cơ sở dữ liệu; một changeset không gắn dbms có thể đủ điều kiện trên nhiều DBMS, nhưng SQL còn cần tương thích.
- **Rollback**: cần lập kế hoạch riêng cho các thay đổi được chọn bởi filter, tránh giả định rằng một filter dùng khi update sẽ tự đảm bảo rollback chỉ tác động đúng những thay đổi tương ứng.

Ví dụ, một changeset có **labels: dev-fixture** vẫn có thể chạy nếu người triển khai không truyền label filter. Nếu dữ liệu đó không được phép xuất hiện ở production, phải thiết kế thêm rào chắn phù hợp: tách migration test, dùng context bắt buộc khi phiên bản hỗ trợ, kiểm soát artifact và cấu hình, cùng quyền thực thi trên môi trường thật.

## 11. Spring Boot: thiếu cấu hình lọc dễ gây hiểu nhầm

Khi tích hợp Liquibase với Spring Boot, ứng dụng có thể tự thực hiện migration lúc khởi động nếu Liquibase được bật và cấu hình phù hợp. Bộ lọc cần được cấu hình rõ ràng cho môi trường cần chọn lọc.

Ví dụ minh họa cho môi trường có context **prod** và đợt phát hành **release-2026**:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
    contexts: prod
    label-filter: release-2026
~~~

Tên property có thể khác giữa các thế hệ Spring Boot/Liquibase; hãy kiểm tra đúng phiên bản đang triển khai. Giá trị môi trường nên được cung cấp từ cấu hình release được kiểm soát, không sao chép mặc định dev sang production.

Nếu bỏ **contexts** và **label-filter**, ứng dụng thường gọi Liquibase mà không áp điều kiện lọc tương ứng. Khi đó, các changeset có context thông thường hoặc label vẫn có thể đủ điều kiện, tương tự nguyên tắc mặc định đã phân tích. Đặc biệt, **thiếu property không có nghĩa là tự suy ra context từ Spring profile**. Nếu tổ chức muốn dùng **spring.profiles.active** để quyết định context Liquibase, phải cấu hình ánh xạ có chủ đích và kiểm tra trên artifact thật.

Với nhiều instance Spring Boot cùng khởi động, Liquibase có cơ chế khóa phục vụ quá trình migration, nhưng khóa không thay thế chính sách chọn đúng context/label. Một instance chạy thiếu filter vẫn có thể chọn những changeset khác dự kiến. Với hệ thống lớn, việc chạy migration bằng một job triển khai chuyên trách có cấu hình tường minh thường giúp dễ kiểm soát và truy vết hơn.

## 12. CI/CD: biến bộ lọc thành đầu vào có kiểm chứng

Trong CI/CD, lỗi phổ biến là script lấy một biến môi trường rỗng rồi bỏ tùy chọn filter:

~~~text
DEPLOY_CONTEXT = prod
RELEASE_LABEL   = release-2026
~~~

Nếu biến bị thiếu vì lỗi cấu hình, lệnh cuối có thể trở thành **liquibase update** không có filter. Với changelog chứa changeset context thông thường hoặc label, kết quả đủ điều kiện có thể **rộng hơn** mong đợi.

Quy trình triển khai nên:

1. **Quy định filter bắt buộc** cho từng môi trường khi đó là yêu cầu của hệ thống.
2. **Kiểm tra biến không rỗng** và thuộc tập giá trị được phép trước khi xây lệnh update.
3. **In cấu hình không nhạy cảm** vào log phát hành: môi trường, context filter, label filter, phiên bản Liquibase, đường dẫn changelog và commit/artifact.
4. **Chạy validate, status và update-sql** bằng chính tham số sẽ được dùng khi triển khai.
5. **Duyệt danh sách changeset dự kiến**; xác nhận không có thay đổi test/dev hoặc thay đổi ngoài release.
6. **Chạy update một lần có kiểm soát** và lưu bằng chứng lịch sử triển khai.
7. **Kiểm tra DATABASECHANGELOG và trạng thái schema/dữ liệu** để xác nhận những thay đổi đã áp dụng.

Nếu định nghĩa hệ thống yêu cầu filter không được thiếu, hãy cấu hình pipeline **fail closed**: thiếu context hoặc label cần thiết thì dừng trước khi gọi Liquibase. Không mặc định hy vọng Liquibase sẽ coi thiếu filter là “chặn tất cả”.

Khi dùng nhiều trục lọc, nên tài liệu hóa rõ mỗi trục làm gì. Ví dụ, **context=prod** biểu diễn môi trường, còn **label=release-2026** biểu diễn phạm vi release. Không đặt cả hai vào một biến “environment” khó kiểm chứng.

## 13. Những lỗi tư duy thường gặp

| Nhận định sai | Thực tế cần nhớ | Hướng khắc phục |
|---|---|---|
| “Không truyền filter thì Liquibase không chạy changeset có context/label” | Context thông thường và label không tự chặn khi thiếu filter | Chạy thử update-sql với cấu hình trống và xem kết quả |
| “Label filter chỉ chọn đúng changeset có label trùng” | Changeset **không có label** vẫn đủ điều kiện lọc label | Tách phạm vi changelog hoặc bổ sung chiến lược chọn lọc |
| “Đã có label dev nên production không thể chạy” | Nếu không truyền label filter, label có thể không giới hạn changeset | Kiểm soát cấu hình pipeline và các điều kiện môi trường |
| “Chỉ cần contextFilter=dev là đủ an toàn” | Nếu không truyền context filter, context thông thường vẫn có thể chạy | Dùng context tường minh bằng **@** khi phù hợp; kiểm chứng runtime |
| “Truyền context prod thì label release cũng được tự kiểm tra” | Context và label được xét riêng | Truyền đầy đủ các filter cần thiết |
| “Changeset bị filter bỏ qua là đã được đánh dấu chạy” | Changeset bị bỏ qua thường không được ghi lịch sử đã thực thi | So sánh DATABASECHANGELOG trước/sau các lần update |
| “Chạy update-sql thành công nghĩa là dữ liệu an toàn” | SQL sinh ra mới là kế hoạch; còn precondition, transaction và DBMS thực tế | Thử update trên database đại diện và kiểm tra kết quả |
| “Spring profile tự động chính là Liquibase context” | Không có ánh xạ mặc định chung phải dựa vào trong mọi dự án | Cấu hình Spring Liquibase tường minh và kiểm tra artifact |

## 14. Bài thực hành có kiểm chứng

Thực hành trên database tạm hoặc schema thử nghiệm, dùng changelog mẫu ở mục 7. Giữ một bản sao trạng thái ban đầu để mỗi kịch bản được chạy công bằng.

**Kịch bản A — Không truyền filter**

- Dự đoán changeset được chọn: **001, 002, 004, 006**.
- Dự đoán changeset bị loại: **003, 005** vì **@dev**.
- Chạy **update-sql**, kiểm tra danh sách changeset/SQL.
- Thực thi trên database thử nghiệm mới; xác nhận bảng **filter_demo** có các dòng ID **2, 4, 6**.

**Kịch bản B — Context prod, không label filter**

- Dự đoán changeset được chọn: **001, 004, 006**.
- Dự đoán dữ liệu: ID **4, 6**.
- Giải thích vì sao nhãn **release-2026** ở changeset 004 không chặn nó.

**Kịch bản C — Context dev, label hotfix**

- Dự đoán changeset được chọn: **001, 002, 003, 006**.
- Dự đoán dữ liệu: ID **2, 3, 6**.
- Giải thích vì sao changeset 003 được chọn dù không có label.

**Kịch bản D — Cập nhật lại cùng database**

- Trên database đã hoàn thành kịch bản A, chạy lại với context **dev**.
- Chỉ xem xét các changeset còn chưa được ghi lịch sử; trong ví dụ, changeset **003** và **005** nay có thể trở nên đủ điều kiện.
- Đối chiếu kết quả với DATABASECHANGELOG và dữ liệu thực tế.
- Giải thích vì sao lần chạy thứ hai không lặp lại toàn bộ SQL đã chạy ở kịch bản A.

Khi chạy các bài thử, luôn chú ý phiên bản Liquibase và kiểu changelog đang dùng; nếu CLI của dự án có tên option khác, thay theo tài liệu phiên bản. Không dùng dữ liệu production cho bài thực hành.

## 15. Checklist trước khi triển khai

Trước khi chạy migration có context hoặc label, hãy xác nhận:

- Đã biết **contextFilter** và **labels** của từng changeset cần triển khai.
- Đã xác nhận **context filter** và **label filter** thực sự được truyền ở runtime, thay vì chỉ tồn tại trong tài liệu pipeline.
- Đã đánh giá tác động của **không truyền filter** trên các changeset có context thường và labels.
- Đã nhận diện changeset **không có nhãn/context**: chúng thường vẫn đủ điều kiện dù bộ lọc được truyền.
- Đã xác nhận phiên bản Liquibase hỗ trợ cú pháp **@context** nếu dùng để yêu cầu lựa chọn tường minh.
- Đã phân biệt thay đổi bị bỏ qua bởi filter với thay đổi đã ghi nhận trong **DATABASECHANGELOG**.
- Đã chạy **update-sql** trên database có lịch sử phù hợp, kiểm tra changeset dự kiến và thử thực thi trên môi trường đại diện.
- Đã kiểm tra Spring Boot và CI/CD không âm thầm bỏ option khi giá trị cấu hình rỗng.
- Đã xác nhận precondition, dbms, rollback và quyền triển khai cho những thay đổi có rủi ro cao.

**Kết luận:** Trong Liquibase, **không có context/label filter thường mở rộng phạm vi lựa chọn**, còn **changeset không gắn nhãn vẫn được coi là thay đổi áp dụng chung** và không bị chặn chỉ vì người chạy truyền một label filter. Context có tiền tố **@** là ngoại lệ yêu cầu chỉ định context phù hợp khi thực thi. Hiểu rõ các mặc định này, kiểm chứng bằng runtime thực tế và buộc pipeline khai báo những filter cần thiết sẽ giúp giảm nguy cơ triển khai nhầm dữ liệu hoặc schema qua nhiều môi trường.

