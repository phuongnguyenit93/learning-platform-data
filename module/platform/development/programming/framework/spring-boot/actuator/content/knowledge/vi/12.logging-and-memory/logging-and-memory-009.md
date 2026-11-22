# Thu thập và lưu trữ dump an toàn để phân tích ngoài ứng dụng

## 1. Từ triệu chứng đến bằng chứng có thể mang đi phân tích

Khi ứng dụng Spring Boot phản hồi chậm, nhiều luồng bị chặn hoặc bộ nhớ tăng liên tục, log thường chỉ cho biết điều đã được ghi lại. Bản chụp chẩn đoán (dump) bổ sung trạng thái của JVM tại một thời điểm. Có thể thu thập bản chụp, chuyển sang máy phân tích được kiểm soát rồi điều tra mà không bắt ứng dụng phục vụ cả công việc phân tích nặng.

Trong chương **Log và bộ nhớ**, mục tiêu của bài này là giữ được bằng chứng đúng, đủ và an toàn từ lúc yêu cầu tạo dump đến khi hết thời hạn lưu trữ. Việc tạo dump vẫn tác động đến JVM đang chạy; chỉ phần đọc, lập chỉ mục và phân tích được chuyển ra ngoài ứng dụng.

Luồng công việc nên là:

```text
Triệu chứng + đúng JVM + quyền thu thập
  → chọn loại dump và thời điểm
  → tải vào vùng riêng, chưa coi là tệp hoàn chỉnh
  → kiểm tra + ghi thông tin nguồn + tính mã băm
  → mã hóa + chuyển qua kênh được kiểm soát
  → xác minh tại máy nhận + phân tích trên bản làm việc
  → thu hồi quyền + xử lý các bản sao khi hết hạn
```

Không cần tạo cả thread dump và heap dump cho mọi sự cố. Chọn bằng chứng theo câu hỏi điều tra trước khi chọn endpoint.

## 2. Phân biệt loại dump và giới hạn của từng loại

| Loại bằng chứng | Câu hỏi phù hợp | Lưu ý khi thu thập |
| --- | --- | --- |
| Thread dump | Luồng đang chạy ở đâu, chờ khóa nào, có nhiều luồng cùng bị chặn không? | Có thể lấy một chuỗi vài bản cách nhau một khoảng thời gian để so sánh. |
| Heap dump | Những đối tượng nào đang chiếm hoặc giữ lại nhiều bộ nhớ? | Tệp có thể lớn, chứa dữ liệu nghiệp vụ và gây gián đoạn khi tạo. |
| Log và số liệu vận hành cùng thời điểm | Sự cố xảy ra khi nào, ở bản triển khai nào, tải và GC thay đổi ra sao? | Chọn phần liên quan, tránh gom toàn bộ dữ liệu chỉ vì tiện. |

Thread dump là ảnh chụp các luồng, không phải lịch sử đầy đủ của mọi lời gọi. Heap dump là ảnh chụp đồ thị đối tượng, không phải bản sao đầy đủ của tiến trình hay toàn bộ bộ nhớ hệ điều hành. RSS tăng do bộ nhớ native hoặc direct buffer không nhất thiết được giải thích hoàn toàn bằng heap dump.

Với Spring Boot 3.3, `GET /actuator/threaddump` trả được JSON hoặc văn bản khi yêu cầu `Accept: text/plain`. `GET /actuator/heapdump` trả dữ liệu nhị phân; HotSpot dùng HPROF, OpenJ9 dùng PHD. Chọn công cụ đọc tương thích với JVM và định dạng thực tế, không suy ra định dạng chỉ từ đuôi tệp. Nguồn: [Thread Dump API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/threaddump.html), [Heap Dump API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/heapdump.html).

## 3. Vì sao dump cần được bảo vệ ngay từ lúc tạo?

Heap có thể giữ mật khẩu đang được xử lý, token, khóa, chuỗi kết nối, nội dung yêu cầu, thông tin khách hàng hoặc dữ liệu đã giải mã. Không phải mọi bí mật chắc chắn xuất hiện, nhưng không được coi dump là dữ liệu vô hại chỉ vì nó không phải cơ sở dữ liệu.

Thread dump thường không chứa toàn bộ giá trị biến cục bộ, nhưng tên luồng, stack trace, tên lớp, đường dẫn hoặc tên tác vụ do ứng dụng đặt vẫn có thể tiết lộ thông tin nội bộ. Báo cáo do công cụ phân tích tạo ra cũng có thể trích chuỗi nhạy cảm.

Việc che giá trị trong endpoint `env`, trong log hoặc trong giao diện không tự động che cùng giá trị bên trong heap dump. Đổi tên tệp, nén ZIP/GZIP hoặc chuyển sang đuôi khác cũng không phải mã hóa. Không đưa dump thô vào Git, thư mục static, thư mục tải công khai, ticket mở rộng quyền xem hoặc dịch vụ phân tích bên ngoài khi chưa được phép.

Cần bảo vệ đồng thời ba thuộc tính:

- **Tính bí mật:** ai được tạo, tải, đọc và giải mã dump?
- **Tính toàn vẹn:** tệp phân tích có đúng các byte đã thu thập không?
- **Khả năng truy nguyên:** bản chụp đến từ JVM nào, thời điểm nào và theo yêu cầu điều tra nào?

## 4. Chuẩn bị một cửa sổ thu thập có giới hạn

### 4.1. Chọn đúng tiến trình và cân nhắc chi phí

Trước khi gọi endpoint, xác định ứng dụng, môi trường, bản triển khai, instance/pod, thời điểm UTC và triệu chứng cần giải thích. Trong hệ thống nhiều bản sao, gọi qua bộ cân bằng tải có thể lấy thread dump của instance A và heap dump của instance B. Dùng đường quản trị cố định đến đúng instance hoặc cơ chế định tuyến đã được xác minh.

Với triệu chứng luồng, có thể bắt đầu bằng ba thread dump cách nhau khoảng 5–10 giây. Đây là lựa chọn điều tra, không phải chu kỳ bắt buộc của Actuator. Nếu cùng một nhóm luồng bị kẹt ở cùng vị trí qua nhiều bản, bằng chứng mạnh hơn một ảnh chụp đơn lẻ.

Với heap dump, đánh giá trước độ trễ có thể chấp nhận, dung lượng đĩa, giới hạn container và khả năng tiếp tục phục vụ. Một thao tác HTTP `GET` vẫn có thể gây công việc chẩn đoán tốn tài nguyên. Không đặt endpoint này vào health check hoặc lịch scrape giám sát.

Phân biệt **đĩa của JVM tạo dump** với **đĩa của máy tải dump**. Trong triển khai HotSpot của Spring Boot 3.3, dump được tạo thành tệp tạm ở phía máy chủ trước khi gửi về. Vì vậy, máy tải còn chỗ không có nghĩa máy chủ cũng còn chỗ. Kiểm tra nơi JVM dùng cho tệp tạm; `/tmp` gắn bằng tmpfs hoặc volume dùng bộ nhớ có thể làm tăng áp lực bộ nhớ thay vì giải quyết nó.

Không ước lượng kích thước dump bằng đúng `-Xmx` rồi coi là giới hạn chắc chắn. Cần dự phòng cho tệp tạm, bản tải xuống, bản mã hóa và tệp chỉ mục của công cụ phân tích. Đặt ngưỡng và thời gian thu thập dựa trên môi trường thực tế.

### 4.2. Tách ba điều kiện truy cập Actuator

Với Spring Boot 3.3, cần phân biệt endpoint được **bật**, được **công bố qua HTTP** và người gọi được **xác thực/phân quyền**. Mặc định HTTP chỉ công bố `health`. Cấu hình sau là một phần bổ sung cho ứng dụng đã có Actuator, không phải cấu hình bảo mật hoàn chỉnh:

```yaml
management:
  server:
    port: 9091
  endpoints:
    web:
      exposure:
        include: "health,threaddump,heapdump"
  endpoint:
    threaddump:
      enabled: true
    heapdump:
      enabled: true
```

Nguồn về cấu hình và bảo mật endpoint: [Spring Boot 3.3 — Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Cổng `9091` ở ví dụ phải được giới hạn bằng mạng quản trị, firewall hoặc gateway; tách cổng tự nó không tạo ra cơ chế bảo vệ. Áp dụng quyền riêng cho người vận hành cần thu thập dump và dùng TLS trên đường truyền. Khi ứng dụng có cấu hình Spring Security riêng, kiểm tra trực tiếp quy tắc dành cho Actuator, không giả định thêm dependency là đủ.

Không mở `include: "*"` chỉ để lấy một dump. Nếu endpoint chỉ được mở tạm cho sự cố, ghi rõ thời điểm đóng và cách khôi phục cấu hình. Cấu hình YAML trên dành cho dòng 3.3; không áp dụng máy móc các thiết lập `access` của phiên bản mới hơn vào ứng dụng này.

## 5. Tải xuống có kiểm tra, không ghi nhận nhầm tệp lỗi

### 5.1. Điều kiện của ví dụ

Ví dụ dưới đây là **script Bash cho Linux**, chạy trên máy thu thập được phép truy cập mạng quản trị. Cần có `curl`, `mktemp`, `date`, `wc`, `grep`, `head`, `mv`, `sleep` và `sha256sum`. Đây không phải mã PowerShell và không phải lệnh được chạy trên máy sản xuất chỉ để học bài.

Giả định endpoint HTTPS đã được định tuyến đến **một instance cụ thể**, không chuyển hướng sang trang đăng nhập, dùng HTTP Basic với tài khoản có quyền chẩn đoán. Nếu môi trường dùng mTLS hoặc cơ chế khác, thay cấu hình xác thực theo quy trình của môi trường đó.

Trước khi chạy:

- Đặt `CAPTURE_ROOT` thành thư mục riêng thuộc người thu thập, có quyền `700`, nằm trên vùng lưu trữ được kiểm soát và còn đủ chỗ.
- Đặt `ACTUATOR_BASE` thành URL HTTPS thật của instance, ví dụ dạng `https://ops.example.com:9443/actuator`; không thêm dấu `/` cuối.
- Đặt `ACTUATOR_NETRC` thành đường dẫn tuyệt đối tới tệp netrc đã được cấp an toàn, quyền `600`, chỉ chứa thông tin xác thực cần cho máy chủ đó. Không chép tệp này vào gói dump. Không nhập mật khẩu trực tiếp trong dòng lệnh hoặc bật `set -x`.
- Đặt `INCIDENT_ID`, `INSTANCE_ID`, `DEPLOYMENT_ID` thành mã nhận diện nội bộ không chứa bí mật. Thông tin phiên bản JVM được bổ sung vào biên bản điều tra từ nguồn vận hành đã xác minh.

Không có tài khoản/mật khẩu mẫu trong bài. Các biến trên là đầu vào phải cung cấp; script dừng ngay nếu thiếu.

### 5.2. Script thu thập

```bash
#!/usr/bin/env bash
set -euo pipefail
umask 077

: "${CAPTURE_ROOT:?Can thu muc thu thap rieng}"
: "${ACTUATOR_BASE:?Can URL HTTPS cua dung instance}"
: "${ACTUATOR_NETRC:?Can tep netrc duoc cap an toan}"
: "${INCIDENT_ID:?Can ma su co}"
: "${INSTANCE_ID:?Can ma instance}"
: "${DEPLOYMENT_ID:?Can ma ban trien khai}"

[[ -d "$CAPTURE_ROOT" && -w "$CAPTURE_ROOT" ]]
[[ -r "$ACTUATOR_NETRC" ]]
[[ "$ACTUATOR_BASE" == https://* ]]

capture_dir=$(mktemp -d "$CAPTURE_ROOT/capture.XXXXXXXX")
chmod 700 "$capture_dir"

printf 'incident=%s\ninstance=%s\ndeployment=%s\n' \
  "$INCIDENT_ID" "$INSTANCE_ID" "$DEPLOYMENT_ID" \
  > "$capture_dir/metadata.txt"
printf 'collection_started_utc=%s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$capture_dir/metadata.txt"

fetch_dump() {
  local endpoint="$1"
  local accept="$2"
  local filename="$3"
  local timeout_seconds="$4"
  local part="$capture_dir/$filename.part"
  local http_code started finished

  started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  if ! http_code=$(curl --disable \
    --silent --show-error --fail \
    --proto '=https' \
    --connect-timeout 10 --max-time "$timeout_seconds" \
    --netrc-file "$ACTUATOR_NETRC" \
    --header "Accept: $accept" \
    --output "$part" --write-out '%{http_code}' \
    "$ACTUATOR_BASE/$endpoint"); then
    printf 'Tai that bai; tep .part chua duoc cong nhan: %s\n' \
      "$filename" >&2
    return 1
  fi

  if [[ "$http_code" != 200 || ! -s "$part" ]]; then
    printf 'HTTP khong hop le hoac tep rong: %s\n' \
      "$filename" >&2
    return 1
  fi

  case "$filename" in
    thread-*.txt)
      if ! grep -Fq 'java.lang.Thread.State:' "$part"; then
        printf 'Khong nhan dien duoc thread dump van ban\n' >&2
        return 1
      fi
      ;;
    heap.hprof)
      if [[ "$(head -c 12 "$part")" != 'JAVA PROFILE' ]]; then
        printf 'Khong nhan dien duoc dau tep HPROF\n' >&2
        return 1
      fi
      ;;
  esac

  mv -- "$part" "$capture_dir/$filename"
  finished=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  printf 'file=%s start_utc=%s end_utc=%s bytes=%s\n' \
    "$filename" "$started" "$finished" \
    "$(wc -c < "$capture_dir/$filename")" \
    >> "$capture_dir/metadata.txt"
}

for sample in 1 2 3; do
  fetch_dump 'threaddump' 'text/plain' "thread-$sample.txt" 120
  if [[ "$sample" != 3 ]]; then
    sleep 5
  fi
done

# Chi bat dong nay sau khi da danh gia chi phi va can heap dump.
if [[ "${CAPTURE_HEAP:-no}" == yes ]]; then
  fetch_dump 'heapdump?live=true' \
    'application/octet-stream' 'heap.hprof' 600
fi

printf 'collection_finished_utc=%s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$capture_dir/metadata.txt"

(
  cd "$capture_dir"
  files=(metadata.txt thread-1.txt thread-2.txt thread-3.txt)
  if [[ -f heap.hprof ]]; then
    files+=(heap.hprof)
  fi
  sha256sum "${files[@]}" > SHA256SUMS
  sha256sum -c SHA256SUMS
)

printf 'Thu thap hoan tat: %s\n' "$capture_dir"
```

Chạy script với `CAPTURE_HEAP=yes` chỉ khi cần heap dump và đã chấp nhận chi phí. Mặc định script chỉ lấy ba thread dump. `120` và `600` giây là ngân sách mẫu của phía tải xuống, không phải thời gian hoàn thành được Actuator bảo đảm.

Script dùng tên tệp cố định trong thư mục ngẫu nhiên riêng, ghi vào `.part` trước rồi mới đổi tên. Không dùng tên do HTTP header cung cấp để quyết định đường dẫn. `curl --disable` nằm đầu các tùy chọn để không đọc cấu hình curl mặc định có thể làm thay đổi hành vi. Không bật theo chuyển hướng, retry tự động hoặc bỏ kiểm tra chứng chỉ TLS. Chi tiết các tùy chọn: [curl manual](https://curl.se/docs/manpage.html).

Kiểm tra HTTP `200`, kích thước khác không và dấu hiệu nhận diện giúp phát hiện nhiều lỗi thường gặp, chẳng hạn tải nhầm trang đăng nhập. Đây chỉ là sàng lọc: một tệp có đầu HPROF đúng vẫn có thể bị cắt cụt; cần mở thành công bằng trình phân tích tương thích để xác nhận thêm. Mã băm của một tệp hỏng vẫn được tính bình thường.

Đầu ra `sha256sum -c` khi chỉ thu thập thread dump có dạng:

```text
metadata.txt: OK
thread-1.txt: OK
thread-2.txt: OK
thread-3.txt: OK
Thu thap hoan tat: <thu muc capture vua tao>
```

Dòng đường dẫn là giá trị thay đổi theo lần chạy; khi có heap dump hợp lệ, có thêm `heap.hprof: OK`. Không có một mã SHA-256 cố định để đưa vào bài vì dump chứa dữ liệu thay đổi theo thời điểm.

### 5.3. Phạm vi HotSpot và hành vi khi lỗi

Nhánh heap trong script dành cho **HotSpot**: `live=true` chọn các đối tượng còn có thể truy cập được; không có nghĩa là truyền dữ liệu liên tục, che bí mật hoặc bảo đảm ít ảnh hưởng. Trong mã Spring Boot 3.3.13, HotSpot mặc định dùng `true` nếu không truyền tham số này; OpenJ9 không hỗ trợ truyền `live`. Vì vậy không dùng nguyên nhánh HotSpot cho OpenJ9: cần bỏ tham số, chọn tên/kiểm tra phù hợp PHD và kiểm chứng bằng công cụ đọc tương ứng. Nguồn: [HeapDumpWebEndpoint 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/management/HeapDumpWebEndpoint.java).

Nếu lỗi xảy ra, script dừng và giữ các tệp trong thư mục riêng để người vận hành xử lý có chủ đích. Tệp `.part` vẫn có thể chứa dữ liệu thật và phải được bảo vệ như dump hoàn chỉnh. Không chuyển thư mục có lần thu thập thất bại thành gói bằng chứng hoàn tất.

Timeout hoặc việc ngắt kết nối của máy tải **không chứng minh** JVM đã hủy công việc tạo dump. Kiểm tra trạng thái JVM, tài nguyên và tệp tạm phía máy chủ trước khi yêu cầu lại. Retry tự động có thể tạo thêm nhiều bản chụp lớn đúng lúc hệ thống đang quá tải.

## 6. Khi HTTP không phải đường thu thập phù hợp

Nếu ứng dụng không phục vụ được HTTP nhưng người vận hành còn truy cập đúng máy/container và JDK tương thích, có thể cân nhắc công cụ JVM. Các lệnh sau là ví dụ Bash cho HotSpot, với `TARGET_PID` đã xác minh, `SERVER_CAPTURE_DIR` là thư mục riêng mà tài khoản JVM ghi được và đủ dung lượng:

```bash
: "${TARGET_PID:?Can PID da xac minh}"
: "${SERVER_CAPTURE_DIR:?Can thu muc phia JVM}"
jcmd "$TARGET_PID" Thread.print -l \
  > "$SERVER_CAPTURE_DIR/threads.txt"
jcmd "$TARGET_PID" GC.heap_dump \
  "$SERVER_CAPTURE_DIR/heap.hprof"
```

`jcmd` yêu cầu quyền truy cập tiến trình phù hợp và chạy cùng máy với JVM; với container phải xét đúng không gian PID và các giới hạn attach. Theo tài liệu JDK 21, `GC.heap_dump` có mức tác động cao và yêu cầu full GC trừ khi dùng `-all`. Không tự thêm `-all` để “nhanh hơn” vì nó thay đổi tập đối tượng được ghi. Nguồn: [JDK 21 — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).

Đường dẫn heap dump là đường dẫn nhìn từ tiến trình JVM; dấu `>` của lệnh thread dump là chuyển hướng của shell gọi lệnh. Nếu shell và JVM ở hai môi trường tệp khác nhau, không được suy ra hai tệp sẽ nằm cùng nơi. Dump tạo từ `jcmd` vẫn phải đi qua kiểm tra, ghi nguồn, tính mã băm và bảo vệ như dump tải qua Actuator.

`-XX:+HeapDumpOnOutOfMemoryError` có thể hỗ trợ thu thập trước khi can thiệp thủ công, nhưng phải chuẩn bị đường lưu và dung lượng từ trước. Không phải mọi lần container bị hệ điều hành kết thúc do thiếu bộ nhớ đều đi qua Java `OutOfMemoryError` hoặc để lại dump. Không chờ đến sự cố mới coi tùy chọn này là bảo đảm phục hồi bằng chứng.

## 7. Lưu biên bản nguồn và kiểm tra tính toàn vẹn

Mỗi lần thu thập cần một biên bản nhỏ đặt cùng dump, bao gồm:

- Mã sự cố, người chịu trách nhiệm và lý do thu thập.
- Ứng dụng, môi trường, instance/pod, bản triển khai; phiên bản Java và loại JVM đã xác minh.
- Thời gian UTC bắt đầu/kết thúc; tình trạng đồng bộ đồng hồ nếu cần đối chiếu nhiều hệ thống.
- Loại dump, đường thu thập và tham số có ảnh hưởng như `live=true`.
- Tên tệp, kích thước, mã SHA-256; lỗi hoặc khoảng dữ liệu không thu được.
- Nơi lưu được cấp quyền, nhóm người được đọc, thời điểm xem xét/xóa và người sở hữu khóa giải mã.

Script chỉ điền các thông tin nó biết trực tiếp. Bổ sung phần còn lại từ nguồn vận hành, không đoán phiên bản JVM hoặc instance từ tên tệp. Nếu chỉnh `metadata.txt` sau khi tính mã băm, cập nhật lại manifest trước khi mã hóa và ghi nhận việc hoàn thiện biên bản. Không sửa dump gốc để làm nội dung khớp với biên bản.

SHA-256 giúp nhận biết các byte có thay đổi, nhưng tệp dump và tệp checksum cùng bị kẻ khác thay được thì đối chiếu vẫn có thể báo thành công. Khi cần xác minh nguồn gửi, dùng kênh đã xác thực, nhật ký truy cập đáng tin hoặc chữ ký theo quy trình của tổ chức. Mã băm không thay thế xác thực nguồn và cũng không chứng minh dump đầy đủ về mặt ngữ nghĩa.

Giữ một bản gốc đã xác minh, hạn chế quyền sửa; phân tích trên bản làm việc. Không trộn nhiều lần chụp vào cùng tên `heap.hprof` trong một thư mục rồi ghi đè mất mốc trước.

## 8. Mã hóa gói bằng chứng và bàn giao

### 8.1. Quyền truy cập phải tiếp tục sau khi tải

Vùng lưu tạm nên thuộc tài khoản chuyên trách, dùng đĩa được bảo vệ, tránh thư mục tự đồng bộ và backup không kiểm soát. Quyền Unix `700/600` không thay thế ACL của object storage hoặc quyền trên máy người nhận. Chỉ cấp quyền cho người cần điều tra, có thời hạn và có nhật ký đọc/tải.

Với kho đối tượng, dùng bucket/container riêng tư, mã hóa phù hợp và chính sách vòng đời. Nếu phát hành URL tải có chữ ký, coi URL là thông tin cấp quyền: giới hạn thời gian và người nhận, tránh đưa vào log hoặc ticket có nhiều người xem. Dữ liệu vẫn cần được bảo vệ sau khi URL hết hạn.

### 8.2. Ví dụ mã hóa trước khi chuyển

Ví dụ này dùng `age`, `tar` và `sha256sum` trên Linux. Đây là một lựa chọn công cụ minh họa; có thể dùng công cụ mã hóa đã được tổ chức phê duyệt thay thế. Tệp `RECIPIENTS_FILE` phải chứa khóa công khai của đúng người nhận, đã đối chiếu qua kênh tin cậy. Khóa bí mật để giải mã không nằm trong gói gửi.

Chỉ thực hiện sau khi thu thập thành công và kiểm tra manifest. Các biến là đường dẫn thực đã được xác minh; `HANDOFF_ROOT` là thư mục bàn giao riêng có quyền `700`, nằm ngoài `CAPTURE_DIR`:

```bash
set -euo pipefail
umask 077
: "${CAPTURE_DIR:?Can thu muc thu thap thanh cong}"
: "${HANDOFF_ROOT:?Can thu muc ban giao rieng}"
: "${RECIPIENTS_FILE:?Can danh sach khoa cong khai da xac minh}"
[[ -d "$HANDOFF_ROOT" && -w "$HANDOFF_ROOT" ]]
[[ -r "$RECIPIENTS_FILE" ]]

(
  cd "$CAPTURE_DIR"
  sha256sum -c SHA256SUMS
)

handoff_dir=$(mktemp -d "$HANDOFF_ROOT/handoff.XXXXXXXX")
archive="$handoff_dir/evidence.tar.gz.age"
items=(metadata.txt SHA256SUMS thread-1.txt thread-2.txt thread-3.txt)
if [[ -f "$CAPTURE_DIR/heap.hprof" ]]; then
  items+=(heap.hprof)
fi

tar -C "$CAPTURE_DIR" -czf - -- "${items[@]}" \
  | age -R "$RECIPIENTS_FILE" -o "$archive.part"
mv -- "$archive.part" "$archive"

(
  cd "$handoff_dir"
  sha256sum evidence.tar.gz.age > evidence.tar.gz.age.sha256
  sha256sum -c evidence.tar.gz.age.sha256
)
printf 'Goi ma hoa: %s\n' "$archive"
```

`set -o pipefail` giúp bước đóng gói không được coi là thành công nếu `tar` thất bại dù chương trình phía sau đã kết thúc. Danh sách tệp được chỉ rõ để không gom nhầm `.part`, tệp xác thực hoặc tệp khác. Nén giúp giảm dung lượng; chính `age` mới thực hiện mã hóa. Cú pháp công cụ: [age](https://github.com/FiloSottile/age).

Gửi bản mã và checksum qua kênh nội bộ được cấp quyền; xác minh đúng đích đến trước khi truyền. Sau khi nhận, đối chiếu checksum của bản mã, giải mã trên máy được phép, rồi đối chiếu `SHA256SUMS` bên trong. Nếu một bước thất bại, giữ trạng thái “chưa xác minh”, không mở rộng quyền chia sẻ để nhờ người khác thử tùy tiện.

Chỉ giải nén gói từ nguồn đã xác thực vào thư mục trống riêng. Việc có thể giải mã không tự chứng minh ai đã tạo gói: bất kỳ ai có khóa công khai cũng có thể mã hóa gửi đến người nhận.

## 9. Phân tích ngoài ứng dụng mà vẫn giữ giới hạn của bằng chứng

Máy phân tích cần đủ RAM, dung lượng cho chỉ mục và quyền truy cập hạn chế. Dùng công cụ được phê duyệt, đọc đúng định dạng; tránh đồng bộ dump hoặc báo cáo lên dịch vụ đám mây mặc định của công cụ. File chỉ mục, tệp tạm, ảnh chụp màn hình và báo cáo xuất ra đều thuộc phạm vi dữ liệu cần bảo vệ.

Với thread dump, so sánh các bản theo thứ tự thời gian, quan sát vị trí thực thi và quan hệ chờ khóa. Một luồng ở `WAITING` không tự động là lỗi; nhiều luồng rảnh trong nhóm xử lý có thể hoàn toàn bình thường. Ngược lại, một stack trace giống nhau qua nhiều lần chụp cần đặt cạnh tải thực tế, số liệu CPU và log để giải thích.

Với heap dump HotSpot, có thể dùng Eclipse Memory Analyzer (MAT) để tìm nhóm đối tượng giữ lại nhiều bộ nhớ, xem Dominator Tree và truy theo đường tham chiếu đến GC roots. **Shallow size** là kích thước riêng của đối tượng; **retained size** liên quan lượng bộ nhớ được giữ lại thông qua nó. Một collection có kích thước riêng nhỏ vẫn có thể giữ cả tập đối tượng lớn. Tham khảo: [MAT — Dominator Tree](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/concepts/dominatortree.html).

Một heap dump lớn hoặc báo cáo “nghi ngờ rò rỉ” không đủ chứng minh có rò rỉ bộ nhớ. Cần liên hệ với vòng đời dữ liệu, giới hạn cache và diễn biến theo thời gian. Không tạo thêm heap dump trên hệ thống đang nguy cấp chỉ để có bộ so sánh đẹp; quyết định chụp tiếp dựa trên rủi ro và câu hỏi còn thiếu.

Báo cáo điều tra nên dẫn đến bằng chứng cụ thể như thời điểm, tệp, nhóm luồng hoặc chuỗi giữ tham chiếu. Khi chia sẻ kết luận, ưu tiên mô tả đã lược bỏ dữ liệu nhạy cảm; không đính kèm nguyên dump nếu người nhận chỉ cần kết luận.

## 10. Đóng lần thu thập và xử lý các bản sao

Sau bàn giao, xác nhận người nhận đã kiểm tra được bản mã, giải mã được và mở được dump bằng công cụ phù hợp. Sau đó đóng endpoint hoặc đường truy cập tạm đã mở, thu hồi tài khoản/quyền ngắn hạn và ghi nhận nơi còn giữ dữ liệu.

Không coi việc tải xong là đã xóa dump trên máy chủ. Triển khai, phiên bản JVM, đường thu thập và tình huống lỗi có thể để lại tệp phía máy chủ. Kiểm tra đúng tệp/tài khoản/thư mục đã dùng; không xóa cả `/tmp` hoặc volume dùng chung để dọn một sự cố.

Khi hết thời hạn lưu, xét cả bản gốc, `.part`, bản mã, bản giải mã, thư mục làm việc, chỉ mục, báo cáo, snapshot, backup và phiên bản cũ trong kho đối tượng. Với dữ liệu cần giữ làm bằng chứng, áp dụng chính sách bảo toàn phù hợp trước khi xóa. Không hứa rằng xóa một tên tệp hoặc chạy lệnh ghi đè sẽ chắc chắn xóa mọi byte trên SSD, snapshot hay hệ thống có sao lưu.

Lưu nhật ký xử lý và kết luận cần thiết thay cho giữ dump vô thời hạn. Chính sách hoàn tất phải trả lời được: ai đang còn quyền đọc, bản nào còn tồn tại và khi nào từng bản được xử lý.

## 11. Các lỗi thường gặp và cách xử lý

| Hiện tượng hoặc thói quen | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| HTTP `401`/`403` | Thiếu xác thực hoặc thiếu quyền. | Kiểm tra tài khoản và chính sách; không mở endpoint công khai để vượt lỗi. |
| HTTP `404` | Có thể sai cổng/base path, endpoint chưa bật hoặc chưa được công bố. | Xác minh đường quản trị và cấu hình hiệu lực của đúng instance. |
| HTTP `200` nhưng tệp là HTML | Có thể tải trang đăng nhập hoặc nội dung gateway. | Kiểm tra dấu hiệu định dạng và chính sách định tuyến; chưa coi là dump hợp lệ. |
| Kết nối timeout, định chạy lại ngay | JVM có thể vẫn tạo bản chụp; tệp dở dang cũng chứa dữ liệu nhạy cảm. | Kiểm tra phía máy chủ, xử lý `.part`, rồi mới quyết định lần thu thập khác. |
| Lưu vào volume tạm dùng RAM hoặc volume gần đầy | Tạo dump có thể làm tình trạng tài nguyên xấu hơn. | Chuẩn bị đường lưu và hạn mức trước, cân nhắc bằng chứng ít tốn hơn. |
| Gzip rồi gửi qua chat | Nén không bảo vệ nội dung và khó quản lý bản sao. | Mã hóa, giới hạn người nhận và dùng nơi bàn giao được kiểm soát. |
| Checksum đúng nên kết luận tệp chắc chắn đầy đủ | Checksum chỉ xác nhận byte so với giá trị đối chiếu. | Kiểm tra nguồn, định dạng và khả năng đọc bằng trình phân tích. |
| Phân tích trực tiếp trên bản gốc rồi sửa/nén đè | Mất khả năng đối chiếu bằng chứng ban đầu. | Giữ bản gốc đã xác minh, tạo bản làm việc riêng. |
| Chụp qua địa chỉ cân bằng tải | Các tệp có thể đến từ các JVM khác nhau. | Cố định instance và ghi rõ nguồn của từng lần chụp. |

## 12. Thực hành trên môi trường thử nghiệm

Dùng một ứng dụng Spring Boot 3.3 trên HotSpot/JDK 21 với dữ liệu giả. Chuẩn bị đường quản trị HTTPS có xác thực và một instance đã biết, sau đó:

1. Chạy nhánh thread dump; xác minh có ba tệp, thời gian thu thập riêng và manifest kiểm tra thành công.
2. Quan sát một nhóm luồng qua cả ba bản, giải thích đâu là chờ bình thường và đâu là giả thuyết cần kiểm tra thêm. Không kết luận từ tên trạng thái đơn lẻ.
3. Khi tài nguyên cho phép, bật nhánh heap một lần. Mở bản làm việc bằng công cụ hỗ trợ HPROF và ghi lại một chuỗi tham chiếu giữ đối tượng; không dùng dữ liệu khách hàng thật.
4. Mã hóa gói, chuyển trong phạm vi thử nghiệm, đối chiếu checksum trước và sau giải mã. Chỉ người có khóa bí mật tương ứng mới được giải mã.
5. Trên **một bản sao thử nghiệm**, thay đổi một byte rồi chạy kiểm tra checksum; xác nhận kiểm tra không còn thành công. Giữ nguyên bản gốc.
6. Kiểm kê và xử lý các bản sao thử nghiệm, bao gồm `.part`, tệp chỉ mục và quyền tạm đã cấp.

Hoàn thành khi có thể chỉ ra đúng JVM nguồn, giải thích chi phí của thao tác tạo dump, phát hiện tệp tải lỗi, bàn giao một gói đã mã hóa và chứng minh người nhận phân tích đúng bản chụp đã thu thập.
