# Kiểm soát hai lần xuất bản cùng một phiên bản

Trong CI/CD, cùng một sự kiện phát hành có thể được xử lý nhiều lần: webhook được gửi lại, người vận hành bấm chạy workflow hai lần, hai nhánh pipeline cùng tạo release hoặc một job được retry sau timeout. Nếu hai tiến trình cùng xuất bản một package và version, chúng có thể ghi đè tag, tạo metadata không nhất quán hoặc công bố hai nội dung khác nhau dưới cùng một tên phiên bản.

Cần coi việc xuất bản là một thao tác có điều phối. Mỗi artifact coordinate phải có quy tắc định danh bất biến, cơ chế chống xử lý trùng và điểm ghi nhận kết quả có tính nguyên tử. Với cùng một package và version, cùng một nội dung có thể được nhận diện là lần lặp an toàn; nội dung khác phải bị từ chối như một xung đột. Mục tiêu là bảo đảm **một version chỉ đại diện cho một artifact đã được xác minh**.

## 1. Vì sao hai lần xuất bản có thể xảy ra đồng thời?

Pipeline thường được kích hoạt từ nhiều nguồn:

- Push tag release đồng thời với thao tác chạy thủ công.
- Webhook từ Git provider được gửi lại vì lần giao trước timeout.
- Hai workflow khác nhau cùng xử lý một version.
- Hai runner cùng retry sau khi không nhận được phản hồi từ registry.
- Job cũ vẫn đang chạy khi job mới được khởi động.
- Hai nhánh release cùng tạo ra một version do quy ước đặt version không chặt.
- Một người chạy lại job trong lúc lần xuất bản trước chưa kết thúc.

Ví dụ, hai runner cùng kiểm tra package `payments-api:2.8.1` chưa tồn tại. Cả hai đều nhận kết quả “chưa có”, sau đó cùng upload và cập nhật tag. Nếu registry cho phép tag bị ghi đè, nội dung cuối cùng phụ thuộc vào tiến trình hoàn tất sau cùng.

Đây là race condition kiểu **check-then-act**: hai tiến trình kiểm tra cùng một trạng thái rồi cùng hành động dựa trên kết quả cũ. Chỉ kiểm tra trước khi upload không đủ để bảo vệ thao tác ghi cuối cùng.

## 2. Xác định đúng phạm vi cần điều phối

Trước khi chọn lock hoặc queue, cần xác định hai lần chạy có thật sự xung đột hay không. Không nên khóa toàn bộ CI/CD nếu chỉ một package version cần được bảo vệ.

Một khóa xuất bản thường dựa trên artifact coordinate:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| Registry/repository | `registry.example.com` | Phân biệt kho đích |
| Package/image | `payments-api` | Phân biệt sản phẩm |
| Version/tag | `2.8.1` | Định danh release |
| Platform/variant | `linux/amd64` | Phân biệt biến thể nếu publish riêng |
| Channel | `stable`, `candidate` | Phân biệt kênh phát hành nếu có |

Ví dụ khóa logic:

~~~text
publish:registry.example.com/payments-api:2.8.1
~~~

Hai job cùng package và version phải được điều phối. Hai job publish `2.8.1` và `2.8.2` có thể chạy song song nếu registry và quy trình phát hành cho phép. Với image đa kiến trúc, cần khóa ở cấp manifest index hoặc coordinate mà người dùng cuối sẽ pull; chỉ khóa từng platform có thể vẫn để hai tiến trình tranh nhau cập nhật manifest chung.

Cần tách khóa publish khỏi khóa deploy. Xuất bản package và triển khai service là hai tài nguyên khác nhau:

- Publish lock: registry/package/version.
- Deploy lock: environment/service hoặc cluster/namespace/service.
- Migration lock: database/schema.
- Release metadata lock: release record hoặc channel pointer.

Chọn phạm vi quá rộng làm giảm throughput. Chọn quá hẹp có thể không bảo vệ được tài nguyên thực sự đang bị tranh chấp.

## 3. Version đã xuất bản phải bất biến

Một version đã được công bố không nên bị thay nội dung. Tag dễ đọc như `2.8.1` cần được cấu hình bất biến nếu registry hỗ trợ. Khi có bản sửa, hãy phát hành version mới hoặc một prerelease version mới theo quy ước của dự án.

Ví dụ:

~~~text
payments-api:2.8.1  -> sha256:aaa...
payments-api:2.8.2  -> sha256:bbb...
~~~

Nếu hai lần chạy cùng muốn publish `2.8.1`:

- Cùng digest và metadata nguồn gốc tương ứng: có thể coi lần sau là retry trùng và trả về kết quả đã có.
- Khác digest: phải báo conflict và dừng.
- Version đã tồn tại nhưng không thể xác minh digest: không ghi đè; chuyển sang điều tra.
- Tag trỏ đến artifact chưa hoàn chỉnh hoặc thiếu provenance: không coi là release hợp lệ.

Không dùng `latest` làm định danh duy nhất cho release. Tag này thường mang tính di động và có thể trỏ sang version khác. Có thể duy trì tag channel như `stable` hoặc `latest` như một con trỏ cập nhật được, nhưng phải cập nhật nó sau khi version bất biến đã được publish và xác minh thành công.

## 4. Phân biệt duplicate request với version conflict

Một request lặp lại không nhất thiết là lỗi. Điều quan trọng là xác định nó có yêu cầu cùng một kết quả hay đang cố gắng thay đổi nội dung của version đã tồn tại.

| Tình huống | Kết quả nên có |
|---|---|
| Cùng package, version và digest | Idempotent success/no-op sau khi xác minh |
| Cùng package và version nhưng digest khác | Conflict, không ghi đè |
| Cùng version, digest giống nhưng provenance khác | Kiểm tra policy nguồn gốc; không tự thay metadata |
| Version chưa tồn tại | Có thể nhận quyền publish |
| Version đang được một job khác publish | Chờ, trả trạng thái in-progress hoặc lấy kết quả sau |
| Request lặp từ cùng webhook event | Deduplicate theo event/request identity |

Ví dụ, hai webhook cùng thông báo tag `v2.8.1` có thể chỉ là một sự kiện được giao lại. Nếu artifact digest giống nhau, lần chạy thứ hai nên đọc kết quả đã xuất bản và kết thúc như một no-op thành công. Nếu hai commit khác nhau cùng cố dùng version `2.8.1`, đó là lỗi quản lý version và cần được xử lý như conflict.

Không tự động chọn “lần chạy mới nhất thắng”. Điều đó khiến một version đã được tham chiếu trong release note, deployment record hoặc downstream manifest có thể âm thầm đổi nội dung.

## 5. Dùng idempotency key để chống xử lý trùng

Idempotency nghĩa là cùng một yêu cầu được thực hiện nhiều lần nhưng chỉ tạo ra một hiệu ứng cuối cùng. Với publish, có thể tạo idempotency key từ package coordinate:

~~~text
publish:<registry>/<package>:<version>
~~~

Ví dụ:

~~~text
publish:registry.example.com/payments-api:2.8.1
~~~

Khi nhận request, hệ thống ghi nhận key cùng digest, provenance và trạng thái:

- `requested`: đã tiếp nhận yêu cầu.
- `publishing`: một worker đang thực hiện.
- `published`: artifact đã được công bố và xác minh.
- `failed`: lần thực hiện kết thúc với lỗi.
- `conflict`: coordinate đã gắn với nội dung khác.

Khi request trùng đến:

1. Tìm bản ghi theo idempotency key.
2. So sánh digest và metadata cần thiết.
3. Nếu đã published với cùng nội dung, trả lại kết quả cũ.
4. Nếu đang publishing, chờ hoặc trả trạng thái đang xử lý.
5. Nếu nội dung khác, trả conflict.
6. Nếu lần trước failed, chỉ cho retry theo policy và kiểm tra trạng thái registry trước khi tiếp tục.

Idempotency key cần ổn định qua retry. Không tạo key mới theo từng attempt, vì như vậy mỗi lần retry lại trở thành một yêu cầu độc lập.

## 6. Dùng ràng buộc duy nhất để giành quyền publish

Nếu có một database hoặc release service làm nơi điều phối, có thể dùng unique constraint trên coordinate. Cơ sở dữ liệu sẽ phân xử thao tác tạo claim một cách nguyên tử.

Ví dụ schema khái niệm:

~~~sql
CREATE TABLE release_publications (
    registry_name  TEXT NOT NULL,
    package_name   TEXT NOT NULL,
    version        TEXT NOT NULL,
    variant        TEXT NOT NULL DEFAULT '',
    artifact_digest TEXT NOT NULL,
    state          TEXT NOT NULL,
    owner_id       TEXT,
    lease_expires_at TIMESTAMPTZ,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (registry_name, package_name, version, variant)
);
~~~

Khi worker bắt đầu, nó thử tạo bản ghi cho package/version. Nếu insert thành công, worker có claim ban đầu. Nếu bị xung đột khóa chính, worker đọc bản ghi hiện có và so sánh digest/state.

Mẫu thao tác:

~~~sql
INSERT INTO release_publications (
    registry_name,
    package_name,
    version,
    variant,
    artifact_digest,
    state,
    owner_id
)
VALUES (
    'registry.example.com',
    'payments-api',
    '2.8.1',
    'linux-amd64',
    'sha256:aaa...',
    'publishing',
    'runner-8421'
)
ON CONFLICT (registry_name, package_name, version, variant) DO NOTHING;
~~~

Đây là ví dụ PostgreSQL. Ứng dụng cần kiểm tra số dòng được insert và đọc bản ghi hiện tại trong transaction phù hợp. Không chỉ chạy câu SELECT xem version có tồn tại rồi mới INSERT, vì hai worker vẫn có thể cùng nhìn thấy “chưa tồn tại”.

Unique constraint bảo vệ claim trong database, nhưng không tự làm thao tác upload registry trở nên nguyên tử. Bước publish cuối vẫn cần immutable tag, conditional create hoặc cơ chế ghi có điều kiện ở registry.

## 7. Dùng lock khi thao tác xuất bản cần một writer

Lock là cơ chế chỉ cho một tiến trình sở hữu quyền thao tác trên một tài nguyên tại một thời điểm. Lock có thể nằm ở CI platform, database, distributed lock service hoặc release controller.

Một lock cần xác định:

- Resource key: package/version cần bảo vệ.
- Owner: run ID hoặc worker identity.
- Acquisition: cách giành lock nguyên tử.
- Lease/TTL: thời hạn sở hữu nếu worker mất kết nối.
- Renewal: cách gia hạn khi công việc còn chạy.
- Release: cách giải phóng khi hoàn tất.
- Recovery: cách xử lý lock bị bỏ lại sau crash.
- Audit: ai lấy lock, giữ bao lâu và kết quả gì.

Lock phải được giữ trong phạm vi có tranh chấp thực sự. Nếu build mất 15 phút nhưng publish chỉ mất 30 giây, nên build và test trước, sau đó mới lấy lock ngay trước bước kiểm tra coordinate và publish. Điều này giảm thời gian giữ khóa.

Không dùng file lock trên ổ đĩa local của runner để điều phối nhiều máy. Mỗi runner có filesystem riêng; hai runner có thể cùng tạo một file có tên giống nhau mà không biết nhau.

## 8. Distributed lock, lease và fencing token

Distributed lock cần xử lý tình huống worker mất kết nối hoặc bị treo. Một lease có TTL cho phép lock tự hết hạn nếu owner không gia hạn.

Tuy nhiên, chỉ có TTL chưa đủ. Ví dụ:

1. Worker A lấy lock với lease 60 giây.
2. A bị pause lâu hơn 60 giây nhưng process chưa chết.
3. Lease hết hạn, worker B lấy lock mới.
4. A tiếp tục chạy và vẫn cố ghi artifact.
5. A và B cùng thực hiện side effect dù lock service chỉ thấy B đang sở hữu lease.

Đây là vấn đề stale owner. Một giải pháp là **fencing token**: mỗi lần cấp lock tạo một số thứ tự tăng dần. Hệ thống đích chỉ chấp nhận thao tác từ token mới nhất.

~~~text
Worker A receives token 41
Lease A expires
Worker B receives token 42
Registry/release service accepts token 42
Late write from A with token 41 is rejected
~~~

Fencing token chỉ có tác dụng nếu nơi thực hiện side effect kiểm tra token hoặc có một cơ chế tương đương. Nếu registry không hỗ trợ fencing, cần dựa vào immutable version, conditional write và claim nguyên tử ở lớp publish để ngăn stale worker ghi đè.

Lease cần được gia hạn bằng heartbeat. Khi không gia hạn được, worker phải dừng trước khi thực hiện thêm side effect. Không tiếp tục publish chỉ vì process vẫn đang chạy.

## 9. Đừng nhầm lock với atomic publish

Lock giúp điều phối các worker có tuân thủ cùng một giao thức. Nó không đảm bảo artifact không bị ghi một phần, không bị một client khác ghi đè hoặc không bị sửa ngoài pipeline.

Một quy trình publish an toàn nên có hai lớp:

1. **Coordination:** bảo đảm chỉ một worker hợp lệ xử lý coordinate tại một thời điểm.
2. **Atomicity/immutability:** bảo đảm kết quả cuối chỉ xuất hiện khi artifact hoàn chỉnh và version chưa bị chiếm.

Một số registry/object store hỗ trợ thao tác tạo có điều kiện hoặc immutable tag. Có thể upload dữ liệu theo digest trước, xác minh checksum, sau đó tạo manifest/tag cuối bằng thao tác create-if-absent. Nếu coordinate đã tồn tại, đọc lại digest và xử lý theo quy tắc duplicate/conflict.

Không để consumer nhìn thấy một tag đã được tạo nhưng layer hoặc metadata còn thiếu. Nên dùng trạng thái staging/private trong lúc upload, rồi công bố manifest hoặc release record sau khi mọi kiểm tra hoàn tất.

## 10. Quy trình publish an toàn từ build đến công bố

Một flow tham khảo:

~~~mermaid
flowchart TD
    A[Build và test artifact] --> B[Tính digest và tạo provenance]
    B --> C[Acquire publish coordination]
    C --> D{Version đã tồn tại?}
    D -- Cùng digest --> E[Đối chiếu metadata và trả kết quả cũ]
    D -- Digest khác --> F[Conflict, dừng publish]
    D -- Chưa tồn tại --> G[Upload content-addressed artifact]
    G --> H[Verify checksum/signature]
    H --> I[Create version/tag có điều kiện]
    I --> J[Commit release record]
    J --> K[Release lock]
    E --> K
    F --> K
~~~

Một trình tự thực tế:

1. Build artifact và chạy kiểm thử ngoài vùng lock.
2. Tính digest từ nội dung thực tế.
3. Tạo provenance gắn với commit, workflow và build run.
4. Lấy lock hoặc claim cho package/version.
5. Đọc registry và release record hiện có.
6. Nếu cùng digest đã published, trả kết quả idempotent.
7. Nếu digest khác, dừng với conflict.
8. Nếu chưa tồn tại, upload blob/layer theo cơ chế content-addressed.
9. Xác minh checksum, signature và metadata.
10. Tạo version/tag bất biến bằng thao tác có điều kiện.
11. Ghi release record và audit event.
12. Giải phóng lock trong mọi đường kết thúc.

Nếu bước 10 thành công nhưng worker mất kết nối trước khi nhận phản hồi, retry phải đọc lại registry. Không được mặc định upload lại hoặc ghi đè. Trạng thái thực tế ở nơi lưu artifact là nguồn để đối chiếu.

## 11. Ví dụ điều phối publish bằng GitHub Actions concurrency

GitHub Actions có thể giới hạn các workflow/job cùng concurrency group chạy đồng thời. Ví dụ dưới đây dùng group theo repository, package và version:

~~~yaml
name: Publish immutable package

on:
  workflow_dispatch:
    inputs:
      package_name:
        description: Package to publish
        required: true
        type: string
      version:
        description: Immutable release version
        required: true
        type: string
      artifact_digest:
        description: Digest returned by the verified build
        required: true
        type: string

permissions:
  contents: read
  packages: write

jobs:
  publish:
    runs-on: ubuntu-latest
    concurrency:
      group: publish-${{ github.repository }}-${{ inputs.package_name }}-${{ inputs.version }}
      cancel-in-progress: false

    steps:
      - uses: actions/checkout@v4

      - name: Validate release coordinate
        env:
          PACKAGE_NAME: ${{ inputs.package_name }}
          RELEASE_VERSION: ${{ inputs.version }}
          ARTIFACT_DIGEST: ${{ inputs.artifact_digest }}
        run: |
          [[ "$PACKAGE_NAME" =~ ^[a-z0-9][a-z0-9._-]*$ ]]
          [[ "$RELEASE_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9.-]+)?$ ]]
          [[ "$ARTIFACT_DIGEST" =~ ^sha256:[a-f0-9]{64}$ ]]

      - name: Publish only if absent or identical
        env:
          PACKAGE_NAME: ${{ inputs.package_name }}
          RELEASE_VERSION: ${{ inputs.version }}
          ARTIFACT_DIGEST: ${{ inputs.artifact_digest }}
        run: |
          ./scripts/publish-if-absent.sh \
            --package "$PACKAGE_NAME" \
            --version "$RELEASE_VERSION" \
            --digest "$ARTIFACT_DIGEST"
~~~

Ví dụ giả định artifact đã được build, kiểm thử và lưu ở nơi có thể truy xuất bằng digest trước khi job publish chạy. Script publish phải tải/đọc đúng artifact đó, kiểm tra provenance và thực hiện thao tác tạo version an toàn ở registry. Regex chỉ là kiểm tra hình dạng đầu vào; dự án nên dùng parser version và quy tắc tên package phù hợp với registry. Concurrency group không thay thế immutable tag hoặc conditional write.

Có một giới hạn quan trọng: GitHub Actions concurrency group chỉ cho phép một run đang chạy và một run đang chờ trong cùng group; một run mới có thể thay thế run đang chờ. Vì vậy, nó phù hợp để ngăn chạy đồng thời và ưu tiên trạng thái mới nhất, nhưng không phải hàng đợi FIFO bảo đảm mọi yêu cầu đều được xử lý lần lượt. Nếu mọi yêu cầu publish đều phải được giữ lại, hãy dùng queue hoặc release service bền vững.

Với publish đang chạy, `cancel-in-progress: false` tránh chủ động hủy run hiện tại chỉ vì một run mới cùng group xuất hiện. Vẫn cần thiết kế script chịu được timeout, runner mất kết nối và retry.

## 12. Điều phối ở các nền tảng CI khác

Các nền tảng CI có cơ chế điều phối riêng:

| Nền tảng | Cơ chế thường dùng | Lưu ý |
|---|---|---|
| GitHub Actions | `concurrency.group` ở workflow/job | Có một running và một pending; không phải FIFO queue |
| GitLab CI | `resource_group` | Serialize job cùng resource; chọn process mode theo yêu cầu thứ tự |
| Jenkins | Lockable Resources plugin | Khóa tài nguyên dùng chung trong block publish |
| Release service riêng | Durable queue, database claim hoặc distributed lock | Có thể quản lý retry, trạng thái và audit tập trung |

Ví dụ ý tưởng với GitLab CI:

~~~yaml
publish:
  stage: publish
  resource_group: "publish-payments-api-2.8.1"
  script:
    - ./scripts/publish-if-absent.sh --package payments-api --version 2.8.1
~~~

Tên resource group cần được tạo từ package/version thực tế theo quy ước an toàn. Nếu version là biến đầu vào, hãy validate trước khi dùng. Cơ chế resource group serialize job nhưng script vẫn phải kiểm tra version và digest ở registry.

Với Jenkins, có thể dùng lock theo tên resource:

~~~groovy
lock(resource: 'publish-payments-api-2.8.1') {
    sh './scripts/publish-if-absent.sh --package payments-api --version 2.8.1'
}
~~~

Đây là ví dụ cần plugin Lockable Resources và cấu hình resource phù hợp. Không dùng một lock name cố định cho mọi package nếu các release độc lập có thể publish song song.

## 13. Xử lý retry và timeout sau khi publish

Một tình huống khó là registry đã nhận artifact nhưng runner timeout trước khi nhận response. Pipeline không biết publish thành công hay chưa.

Không nên coi timeout đồng nghĩa publish thất bại. Quy trình retry nên:

1. Đọc trạng thái coordinate từ registry và release record.
2. Nếu version đã tồn tại với cùng digest, xác minh metadata rồi trả success.
3. Nếu version chưa tồn tại, kiểm tra upload tạm và tiếp tục theo cơ chế an toàn.
4. Nếu version tồn tại với digest khác, trả conflict.
5. Nếu trạng thái chưa thể xác định, giữ request ở trạng thái pending/unknown và điều tra; không ghi đè để “thử lại”.

Retry cần có giới hạn, exponential backoff và jitter. Nếu registry trả 429 hoặc 503, tôn trọng Retry-After khi có. Nếu lỗi là version conflict, không retry tự động vì nội dung yêu cầu vẫn xung đột.

Mỗi attempt nên có run ID riêng nhưng dùng cùng idempotency key cho một yêu cầu publish logic. Điều này cho phép audit từng lần chạy mà vẫn chống tạo hiệu ứng trùng.

## 14. Hủy job và giải phóng lock an toàn

Job có thể bị hủy do người dùng, timeout, runner crash hoặc workflow mới. Lock không được giữ vĩnh viễn, nhưng giải phóng lock cũng phải an toàn.

Các nguyên tắc:

- Dùng lease/TTL nếu lock service hỗ trợ.
- Gia hạn lock khi publish kéo dài.
- Có cleanup/finally để release khi job kết thúc bình thường.
- Chỉ owner hiện tại mới được release lock của mình.
- Không xóa lock chỉ dựa vào tên resource mà không kiểm tra owner/token.
- Sau khi lock hết hạn, worker cũ phải bị ngăn ghi tiếp bằng fencing hoặc conditional write.
- Kiểm tra trạng thái registry trước khi retry sau cancellation.

Không dựa hoàn toàn vào bước cleanup của CI vì runner có thể bị kill cưỡng bức. Lease xử lý lock bị bỏ lại; fencing/immutable storage xử lý worker cũ vẫn cố ghi sau khi mất quyền.

## 15. Điều phối publish khác với điều phối deploy

Một release thường có ít nhất hai vùng tranh chấp:

- Nhiều job cùng cố publish một package/version.
- Nhiều job cùng triển khai một service lên một môi trường.

Chúng cần lock key riêng:

~~~text
publish:registry.example.com/payments-api:2.8.1
deploy:production:payments-api
migration:production:payments-db
~~~

Hai version khác nhau có thể được build và publish song song. Nhưng hai deployment của cùng service lên production có thể cần tuần tự để tránh ghi đè rollout hoặc làm lệch deployment record.

Không dùng một lock toàn cục cho toàn bộ module CI/CD nếu chỉ cần bảo vệ một tài nguyên. Ngược lại, không dùng lock theo run ID vì mỗi lần chạy sẽ có khóa khác nhau và không ngăn được các run cạnh tranh cùng coordinate.

Nếu một quy trình cần nhiều lock, hãy lấy chúng theo thứ tự cố định để giảm nguy cơ deadlock. Tránh giữ publish lock trong khi chờ approval hoặc chờ một công việc kéo dài không liên quan.

## 16. Kiểm thử các tình huống cạnh tranh

Cơ chế concurrency cần được kiểm thử bằng các lần chạy đồng thời có chủ đích, không chỉ bằng một pipeline đơn lẻ.

| Tình huống | Kết quả mong đợi |
|---|---|
| Hai run cùng package/version/digest | Một lần publish; run còn lại idempotent success |
| Hai run cùng package/version nhưng digest khác | Một run thắng claim; run kia conflict |
| Hai run khác version | Có thể publish song song nếu policy cho phép |
| Webhook giao lại cùng event | Deduplicate, không tạo release thứ hai |
| Runner chết khi đang giữ lock | Lease hết hạn hoặc operator recovery an toàn |
| Lease hết hạn nhưng worker cũ tiếp tục | Write cũ bị fencing/conditional publish từ chối |
| Timeout sau khi registry đã nhận artifact | Retry đọc trạng thái và xác minh, không overwrite |
| Hai workflow dùng hai lock key khác nhau cho cùng resource | Test phải phát hiện cấu hình key sai |
| Tag đã tồn tại nhưng digest khác | Publish thất bại, không force update |
| Publish xong nhưng ghi release metadata lỗi | Reconcile từ registry và hoàn tất metadata idempotently |

Nên chạy thử trên registry hoặc namespace test. Có thể thêm độ trễ có kiểm soát giữa bước kiểm tra và bước ghi để làm lộ race condition. Xác minh cả artifact cuối, digest, release metadata và audit log.

## 17. Theo dõi và điều tra hoạt động publish

Một hệ thống điều phối tốt cần quan sát được trạng thái chờ, khóa và kết quả publish.

Nên ghi nhận:

- Package coordinate và version.
- Artifact digest và provenance reference.
- Idempotency key.
- Workflow run ID, attempt và actor.
- Lock key, owner, fencing token hoặc lease expiry nếu có.
- Thời gian chờ lock và thời gian giữ lock.
- Trạng thái publish và registry response.
- Kết quả duplicate/no-op hoặc version conflict.
- Thời điểm upload, verify và commit release record.
- Lỗi, retry count và kết quả cuối.

Các metric hữu ích:

| Metric | Ý nghĩa |
|---|---|
| Publish lock wait time | Mức độ tranh chấp tài nguyên |
| Concurrent publish conflict count | Số request cùng coordinate cạnh tranh |
| Duplicate request rate | Mức độ webhook/retry trùng |
| Publish duration | Thời gian giữ vùng critical section |
| Stale lease count | Số lock hết hạn bất thường |
| Immutable version conflict | Số lần cố ghi nội dung khác lên version đã tồn tại |
| Reconciliation backlog | Số release cần đồng bộ trạng thái |

Log không nên chứa token registry, password hoặc secret. Dùng run ID, package coordinate và digest để truy vết.

## 18. Checklist kiểm soát hai lần xuất bản cùng version

Trước khi đưa publish workflow vào sử dụng, hãy kiểm tra:

- [ ] Đã xác định artifact coordinate và phạm vi lock.
- [ ] Version đã publish được xem là bất biến.
- [ ] Tag di động như latest không được dùng làm định danh release duy nhất.
- [ ] Cùng version và cùng digest được xử lý idempotently.
- [ ] Cùng version nhưng khác digest bị từ chối như conflict.
- [ ] Có idempotency key ổn định qua các lần retry.
- [ ] Claim được tạo bằng unique constraint hoặc thao tác nguyên tử.
- [ ] Lock có owner, lease/TTL, renewal và recovery.
- [ ] Có fencing token hoặc conditional write để ngăn stale worker.
- [ ] Bước publish cuối có tính atomic hoặc create-if-absent.
- [ ] Upload và xác minh artifact hoàn tất trước khi công bố version.
- [ ] Release metadata được ghi và có thể reconcile sau timeout.
- [ ] CI concurrency group/resource group dùng đúng key.
- [ ] Đã hiểu giới hạn queueing và cancellation của nền tảng CI.
- [ ] Publish lock tách khỏi deploy lock và migration lock.
- [ ] Có test cho hai run đồng thời, retry, timeout và worker crash.
- [ ] Có audit log và metric về lock, conflict và duplicate request.

Kiểm soát xuất bản đồng thời không chỉ là thêm một lock vào pipeline. Cần kết hợp định danh version bất biến, idempotency, claim nguyên tử, điều phối writer và thao tác công bố có điều kiện. Khi hai request cùng đến, hệ thống phải trả lời rõ đó là một lần lặp an toàn hay một xung đột nội dung; không để kết quả phụ thuộc vào runner nào hoàn tất sau cùng.

