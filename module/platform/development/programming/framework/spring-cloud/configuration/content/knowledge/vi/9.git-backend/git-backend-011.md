# Kiểm chứng hành vi khi Git mất kết nối nhưng đã có bản sao cục bộ

Spring Cloud Config Server dùng Git backend thường duy trì một bản sao repository trên máy chủ để đọc các tệp cấu hình. Khi Git remote mất kết nối, bản sao cục bộ có thể vẫn còn nguyên. Tuy nhiên, điều đó **không tự động bảo đảm Config Server sẽ luôn trả về cấu hình cũ**: kết quả phụ thuộc vào thời điểm server cần fetch, `refresh-rate`, trạng thái của bản sao, label được yêu cầu và cách phiên bản Spring Cloud Config xử lý lỗi Git.

Muốn vận hành an toàn, cần kiểm chứng rõ server làm gì khi remote không truy cập được: tiếp tục dùng bản sao hiện tại, trả lỗi, hay đánh dấu unhealthy. Bài này trình bày cách hiểu cơ chế, thiết kế thí nghiệm có kiểm soát và xác định chính sách cho phép hoặc từ chối cấu hình cũ.

## 1. Phân biệt bản sao Git của server với cấu hình trong client

Có hai nơi lưu trạng thái cần phân biệt:

- **Config Server:** Git backend có working copy cục bộ được clone từ remote. Bản sao này cho phép server đọc repository mà không phải tải toàn bộ nội dung ở mọi request.
- **Config Client:** sau khi nạp cấu hình, mỗi ứng dụng có các property source trong Spring `Environment` và các bean đã bind. Việc Git remote mất kết nối không xóa những giá trị đã được nạp trong tiến trình client.

Vì thế, một ứng dụng đang chạy có thể tiếp tục dùng giá trị cấu hình hiện tại ngay cả khi Config Server không truy cập được. Nhưng một ứng dụng mới khởi động, một lần refresh hoặc một request cấu hình mới vẫn có thể cần Config Server và Git backend. Không nên nhầm khả năng tiếp tục chạy với cấu hình đã nạp trong client với khả năng Config Server phục vụ request mới từ bản sao Git.

## 2. Clone, fetch và đọc cấu hình từ working copy

Các thao tác Git có vai trò khác nhau:

| Thao tác | Vai trò |
| --- | --- |
| `clone` | Tạo repository cục bộ lần đầu từ remote |
| `fetch` | Liên hệ remote để lấy thông tin commit/ref mới vào repository cục bộ |
| Checkout/chọn revision | Chuyển đến branch, tag hoặc commit mà request yêu cầu để đọc tệp cấu hình |
| Đọc working copy | Đọc các tệp cấu hình đã có trong repository cục bộ |

Config Server không cần clone lại toàn bộ repository cho mỗi request. Khi đã có working copy, server có thể đọc nội dung cục bộ. Tuy nhiên, backend thường cần kiểm tra hoặc fetch remote để cập nhật branch và label theo chính sách làm mới. Nếu remote không truy cập được đúng lúc cần fetch, request có thể gặp lỗi dù working copy vẫn còn trên đĩa.

Một bản sao cục bộ chỉ có thể cung cấp revision mà nó đã biết. Nếu client yêu cầu một branch, tag hoặc commit mới chưa từng được fetch, bản sao hiện tại không có đủ dữ liệu để đáp ứng yêu cầu đó.

## 3. Vai trò của refresh-rate

Thuộc tính `spring.cloud.config.server.git.refresh-rate` quy định khoảng thời gian tối thiểu giữa các lần cập nhật Git từ remote, tính bằng giây. Giá trị mặc định thường là `0`, nghĩa là server thử cập nhật remote trên mỗi request cấu hình. Khi đặt một giá trị dương, server chỉ thử fetch khi lần cập nhật trước đã cách thời điểm hiện tại ít nhất khoảng thời gian đó.

Ví dụ:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.com/platform/config-repo.git
          default-label: main
          clone-on-start: true
          refresh-rate: 60
```

Với cấu hình này, server có thể dùng working copy hiện có giữa các lần cập nhật remote và chỉ kiểm tra remote lại khi khoảng thời gian tối thiểu đã trôi qua, theo cơ chế của phiên bản đang chạy. Đây không phải lịch fetch nền chạy đều đặn mỗi 60 giây; việc cập nhật thường được kích hoạt khi repository được truy cập.

| Cấu hình | Hành vi dự kiến khi request đến |
| --- | --- |
| `refresh-rate: 0` | Thử fetch remote ở mỗi request |
| `refresh-rate: 60` | Chỉ cần fetch khi đã qua khoảng tối thiểu 60 giây từ lần cập nhật trước; trong khoảng đó có thể dùng working copy hiện tại |

Khoảng thời gian dương có thể giảm số lần gọi Git và cho phép phục vụ dữ liệu cục bộ trong cửa sổ giữa hai lần fetch. Đổi lại, khi remote có commit mới, server có thể chưa thấy commit đó cho đến lần fetch kế tiếp. Giá trị này là lựa chọn về độ mới dữ liệu và tải lên Git server, không phải cơ chế bảo đảm tính sẵn sàng khi remote bị lỗi.

`clone-on-start` và `refresh-rate` giải quyết hai vấn đề khác nhau:

- `clone-on-start` quyết định có khởi tạo repository khi Config Server khởi động hay đợi đến lần đầu backend được truy cập.
- `refresh-rate` kiểm soát khoảng cách tối thiểu giữa các lần fetch cập nhật một repository đã có.

## 4. Điều gì xảy ra khi Git remote mất kết nối?

Không có một kết quả duy nhất cho mọi tình huống. Hãy phân biệt thời điểm lỗi và trạng thái bản sao:

| Tình huống | Điều có thể xảy ra | Cần xác minh |
| --- | --- | --- |
| Chưa có working copy, remote không truy cập được | Clone không thành công; Config Server không thể đọc repository đó | Startup log hoặc lỗi ở request đầu tiên |
| Đã có working copy, request đến trong cửa sổ chưa cần fetch | Server có thể đọc dữ liệu cục bộ mà chưa phải liên hệ remote | HTTP response, `version`, log Git và thời gian từ lần refresh trước |
| Đã có working copy, request kích hoạt fetch nhưng remote lỗi | Request có thể thất bại hoặc backend có thể tiếp tục bằng revision cục bộ tùy phiên bản và đường xử lý lỗi | HTTP status, exception, log và nội dung response của đúng phiên bản |
| Client yêu cầu label chưa có trong bản sao cục bộ | Server không thể đọc revision đó nếu không fetch được remote | Label, refs hiện có và lỗi checkout/fetch |
| Client đã nạp cấu hình trước khi Git mất kết nối | Ứng dụng đang chạy thường tiếp tục giữ các giá trị đã nạp | Hành vi của bean, refresh và lần khởi động mới |

Điểm quan trọng là **không được mặc định rằng Config Server luôn fallback về bản sao cũ khi fetch thất bại**. Hành vi có thể khác giữa phiên bản, loại lỗi Git, cách backend quản lý working copy và cấu hình liên quan. Thiết kế production cần kiểm thử đúng phiên bản và đặt chính sách rõ ràng: cho phép dữ liệu cũ trong giới hạn nào, hay từ chối request khi không thể xác nhận revision mới nhất.

## 5. Cách nhận biết server đang trả về cấu hình cũ

Khi Git remote còn hoạt động, gọi endpoint và lưu metadata từ response:

```bash
curl -sS "http://localhost:8888/billing-api/prod/main"
```

Ghi lại tối thiểu:

- `name`: application mà Config Server đã xử lý.
- `profiles`: profile được áp dụng.
- `label`: label được yêu cầu hoặc giải quyết.
- `version`: với Git backend thường là commit revision đã đọc.
- `propertySources`: các nguồn và khóa cấu hình được trả về.

Sau đó mô phỏng Git remote mất kết nối và gọi lại đúng endpoint. Nếu server trả về response, so sánh `version` và các `propertySources` với lần đầu. Nếu `version` vẫn là commit cũ, server có thể đang phục vụ working copy cũ. Nếu request trả lỗi, ghi nhận HTTP status, exception và log để xác định lỗi xuất hiện ở bước fetch, checkout hay đọc tệp.

`state` có thể xuất hiện trong metadata `Environment` tùy backend, nhưng không nên coi nó là commit SHA hoặc dấu hiệu chắc chắn rằng dữ liệu mới nhất đã được lấy. Với Git, `version` thường hữu ích hơn để ghi nhận commit; vẫn cần kiểm tra nội dung và log khi xác minh outage.

Một response thành công cũng không chứng minh Git remote đang khỏe. Nếu request được phục vụ từ working copy mà không fetch, server có thể trả dữ liệu trong khi remote vẫn mất kết nối. Cần kết hợp kết quả API với log, health indicator và phép kiểm tra kết nối Git độc lập.

## 6. Thiết kế thí nghiệm outage có kiểm soát

Chỉ thực hiện thử nghiệm trên môi trường phát triển hoặc staging, với repository và Config Server riêng. Không ngắt kết nối Git của hệ thống production để kiểm tra hành vi này.

### Chuẩn bị

1. Tạo một Git repository thử nghiệm có thể truy cập bằng Config Server.
2. Đặt một thuộc tính dễ nhận biết, ví dụ `demo.outage.marker: revision-a`, trong `billing-api-prod.yml`.
3. Khởi động Config Server với Git backend và `basedir` riêng cho thí nghiệm.
4. Gọi `/billing-api/prod/main` để buộc clone và xác nhận response chứa `revision-a`.
5. Lưu `version`, `label`, `profiles`, `propertySources`, HTTP status và log của server.

### Kiểm tra khi remote mất kết nối

1. Ngắt đường truy cập tới Git remote bằng cách dừng Git service thử nghiệm hoặc chặn egress của riêng Config Server trong môi trường cô lập.
2. Gọi lại cùng endpoint trong cửa sổ `refresh-rate` nếu đang dùng giá trị dương.
3. Gọi lại sau khi cửa sổ refresh đã hết, hoặc dùng `refresh-rate: 0` để kiểm tra đường fetch trên mỗi request.
4. Ghi HTTP status, thời gian phản hồi, `version`, giá trị marker và log Git.
5. Khôi phục Git remote, thêm commit đổi marker thành `revision-b`, rồi gọi lại endpoint để xác nhận thời điểm server nhìn thấy revision mới.
6. Khởi động một Config Client mới và thử refresh một client đang chạy để phân biệt khả năng phục vụ của server với cấu hình đã được client nạp trước đó.

Đo thời gian request bằng `curl`:

```bash
curl -sS -o response.json \
  -w 'HTTP %{http_code} | Total %{time_total}s\n' \
  'http://localhost:8888/billing-api/prod/main'
```

Không ghi response có bí mật vào file dùng chung. Với thí nghiệm, chỉ dùng marker không nhạy cảm và lưu file ở thư mục tạm dành riêng.

### Ma trận kết quả nên ghi lại

| Trạng thái remote | Refresh đến hạn? | Kết quả cần quan sát |
| --- | --- | --- |
| Online | Có | Server fetch được revision mới và trả metadata tương ứng |
| Online | Chưa đến hạn | Server có thể trả revision trong working copy hiện tại |
| Offline | Chưa đến hạn | Kiểm tra liệu server phục vụ working copy cũ mà không gọi remote |
| Offline | Đến hạn | Ghi nhận request trả lỗi hay trả dữ liệu cũ theo phiên bản thực tế |
| Offline, working copy chưa tồn tại | Không có bản sao | Clone không thể hoàn tất; xác định lỗi ở startup hoặc request đầu tiên |
| Online trở lại | Có request tiếp theo | Xác nhận server fetch được commit mới và response đổi `version`/marker |

Lặp lại thử nghiệm với `clone-on-start: true` và `false` nếu cần kiểm tra cả thời điểm phát hiện lỗi ban đầu. Với mỗi lần thử, dùng `basedir` trống hoặc đã biết trạng thái; nếu tái sử dụng một working copy cũ, phải ghi nhận commit và refs của nó để tránh kết luận sai.

## 7. Ảnh hưởng của basedir và vòng đời triển khai

Config Server cần một thư mục cục bộ để giữ Git working copy. Thuộc tính `spring.cloud.config.server.git.basedir` cho phép chỉ định thư mục này:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.com/platform/config-repo.git
          basedir: /var/lib/config-server/repositories/config-main
```

Nếu dùng thư mục tạm hoặc filesystem của container, working copy có thể mất khi container bị thay thế. Khi khởi động lại trong lúc Git vẫn offline, server có thể không còn bản sao để phục vụ. Nếu cần giữ working copy qua restart, hãy dùng storage bền vững, quyền truy cập phù hợp và chính sách backup/cleanup rõ ràng.

Không nên cho nhiều Config Server instance đồng thời dùng chung một working directory Git nếu chưa có thiết kế khóa và đồng bộ an toàn. Thông thường, mỗi instance nên có working copy riêng hoặc một mô hình lưu trữ được hỗ trợ rõ ràng. Lưu ý rằng giữ bản sao cục bộ qua restart giúp tăng khả năng đọc dữ liệu đã có, nhưng không giải quyết được yêu cầu label chưa từng được fetch hoặc bảo đảm dữ liệu luôn mới nhất.

## 8. Health, readiness và khả năng phục vụ dữ liệu cũ

Một Config Server có thể có HTTP process khỏe nhưng Git backend không thể cập nhật. Ngược lại, health indicator có thể đánh dấu repository không khỏe vì remote không truy cập được, dù working copy cục bộ vẫn có dữ liệu có thể đọc. Cách đánh giá phụ thuộc health contributor, phiên bản và cấu hình của ứng dụng.

Hãy kiểm tra riêng:

- **Liveness:** tiến trình Config Server có còn hoạt động không?
- **Readiness:** instance có được phép nhận request cấu hình mới không?
- **Git connectivity:** server có thể truy cập remote và fetch revision mong muốn không?
- **Configuration serving:** endpoint application/profile/label thực tế có trả về nguồn cấu hình cần thiết không?

Không nên tự động restart Config Server chỉ vì Git tạm thời không truy cập được nếu việc restart sẽ xóa working copy duy nhất còn dùng được. Cũng không nên đánh dấu readiness thành công chỉ vì cổng HTTP mở. Chính sách probe phải phù hợp với mức độ chấp nhận cấu hình cũ và khả năng client tiếp tục khởi động hoặc refresh.

Nếu hệ thống chấp nhận phục vụ cấu hình cũ trong outage, cần xác định rõ giới hạn stale age, cách quan sát revision đang phục vụ, cảnh báo khi không fetch được và cách ngăn dữ liệu cũ kéo dài vô thời hạn. Nếu cấu hình cũ có thể gây rủi ro nghiệp vụ hoặc bảo mật, hãy từ chối request mới khi không xác nhận được revision cần thiết và triển khai phương án khôi phục Git.

## 9. Những yếu tố làm thay đổi kết quả outage

| Yếu tố | Tác động cần xem xét |
| --- | --- |
| `refresh-rate` | Quyết định khi nào request kích hoạt lần fetch tiếp theo |
| `clone-on-start` | Quyết định thời điểm tạo bản sao ban đầu và thời điểm lỗi clone có thể lộ ra |
| `basedir` | Xác định nơi lưu working copy và liệu nó còn sau restart hay không |
| Label yêu cầu | Revision có thể đọc từ local clone hay cần fetch từ remote |
| Credential và TLS/SSH | Có thể remote chỉ mất quyền truy cập do token hết hạn hoặc chứng thư thay đổi |
| Health indicator | Có thể ảnh hưởng readiness dù dữ liệu cục bộ còn đọc được |
| Phiên bản Spring Cloud Config | Có thể ảnh hưởng cách backend xử lý lỗi fetch và phản hồi |
| Số lượng instance | Mỗi instance có thể có cache, thời điểm fetch và revision khác nhau |

Đặc biệt, lỗi xác thực Git khác với lỗi mạng: server có thể phân giải được host nhưng bị từ chối do token hết hạn, quyền bị thu hồi hoặc host key/certificate thay đổi. Log cần được bảo vệ và không được in credential; chỉ ghi mã lỗi và thông tin chẩn đoán an toàn.

## 10. Chính sách vận hành khi Git không khả dụng

Trước khi đưa Config Server vào production, nhóm cần quyết định rõ:

1. Có cho phép trả cấu hình từ working copy cũ không? Nếu có, giới hạn tuổi tối đa là bao lâu?
2. Khi fetch thất bại, request cấu hình mới phải trả lỗi hay được phép tiếp tục bằng revision đã biết?
3. Những ứng dụng nào có thể tiếp tục chạy bằng cấu hình đã nạp, và những ứng dụng nào cần dừng khởi động hoặc refresh?
4. Dùng `basedir` tạm hay storage bền vững? Khi rollout, bản sao cũ có được giữ lại không?
5. Readiness phản ánh trạng thái HTTP, Git remote hay khả năng phục vụ một tập truy vấn cấu hình đại diện?
6. Ai xử lý credential hết hạn, network outage, repository bị force-push hoặc label bị xóa?

Nên lưu metadata `application`, `profiles`, `label`, `version` và thời điểm fetch thành công gần nhất. Thiết lập cảnh báo khi Git fetch thất bại, khi revision phục vụ quá cũ hoặc khi các instance đang trả về những version khác nhau ngoài dự kiến. Không ghi giá trị cấu hình bí mật vào metric, log hoặc cảnh báo.

## 11. Checklist kiểm chứng

- [ ] Đã clone repository thành công và ghi nhận Git revision ban đầu.
- [ ] Đã xác định `refresh-rate`, `clone-on-start` và `basedir` của từng instance.
- [ ] Đã thử request khi remote online, offline trong cửa sổ refresh và offline sau khi refresh đến hạn.
- [ ] Đã xác minh request trả lỗi hay trả cấu hình cũ trên đúng phiên bản Spring Cloud Config.
- [ ] Đã kiểm tra label đã có trong local clone và label chỉ tồn tại trên remote.
- [ ] Đã thử khởi động lại khi remote offline với working copy tạm và working copy bền vững.
- [ ] Đã kiểm tra health, readiness và hành vi của Config Client khi khởi động/refresh.
- [ ] Đã xác định giới hạn tuổi cấu hình cũ, cảnh báo và quy trình khôi phục Git.
- [ ] Đã bảo vệ credential, log và response có thể chứa dữ liệu nhạy cảm.

Khi Git remote mất kết nối, working copy cục bộ là một nguồn dữ liệu có ích, nhưng mức độ sử dụng được của nó phụ thuộc vào thời điểm fetch và trạng thái revision. Chỉ sau khi thử nghiệm outage có kiểm soát trên đúng phiên bản, nhóm mới có thể đặt chính sách stale configuration, readiness và phục hồi phù hợp cho hệ thống Spring Cloud Config.
