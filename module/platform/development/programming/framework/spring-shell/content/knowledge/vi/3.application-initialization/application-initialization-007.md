# Cấu hình chế độ tương tác tường minh theo mặc định của phiên bản

Spring Shell có thể chạy như một terminal tương tác, nơi người dùng nhập nhiều command trong cùng một phiên, hoặc tham gia vào một lần chạy tự động để xử lý command được truyền khi khởi động. Hai cách chạy này phục vụ những tình huống khác nhau. Terminal dành cho người vận hành cần prompt, trợ giúp và khả năng tiếp tục nhập lệnh; tiến trình chạy trong CI, container hoặc script thường cần xử lý đầu vào đã biết rồi kết thúc mà không chờ người dùng.

Khi khởi tạo ứng dụng, hãy xác định rõ chế độ chạy mong muốn và cấu hình theo đúng phiên bản Spring Shell đang dùng. Không nên dựa vào một giá trị mặc định mà nhóm chưa xác minh, vì hành vi mặc định và cách cấu hình có thể thay đổi giữa các dòng phiên bản. Cấu hình tường minh giúp ý định của ứng dụng dễ hiểu, dễ kiểm thử và ít bị ảnh hưởng khi nâng cấp dependency.

## Hiểu hai cách vận hành

### Chế độ tương tác

Trong chế độ tương tác, ứng dụng khởi động một vòng lặp nhận lệnh từ terminal. Người dùng có thể thực hiện nhiều thao tác liên tiếp mà không cần khởi chạy lại tiến trình cho từng command.

Ví dụ một phiên làm việc:

```text
shell:> help
shell:> customer list
shell:> customer show --id 42
shell:> exit
```

Chế độ này phù hợp với công cụ quản trị, CLI dành cho nhân viên vận hành, môi trường phát triển và những thao tác cần khám phá command thông qua trợ giúp. Prompt, lịch sử nhập lệnh, tự hoàn thành và cách thoát phiên là các phần của trải nghiệm tương tác; khả năng cụ thể phụ thuộc cấu hình và phiên bản.

### Chế độ không tương tác

Trong chế độ không tương tác, tiến trình không mở vòng lặp chờ người dùng nhập thêm lệnh. Một command hoặc kịch bản được cung cấp theo cách khởi chạy của phiên bản Spring Shell sẽ được thực thi, sau đó tiến trình trả kết quả và kết thúc.

Ví dụ về ý định gọi một command từ script:

```text
java -jar customer-cli.jar customer show --id 42
```

Kiểu chạy này phù hợp với pipeline CI/CD, cron job, container job và script vận hành. Nó cần có đầu vào rõ ràng, kết quả có thể xử lý bằng máy và mã thoát phản ánh thành công hoặc thất bại. Nếu ứng dụng rơi vào vòng lặp tương tác trong một pipeline không có terminal, tiến trình có thể chờ vô hạn hoặc làm job bị treo.

Hai chế độ mô tả cách ứng dụng nhận và xử lý lệnh. Chúng không quyết định command nào được đăng ký, command có quyền làm gì hay quy tắc nghiệp vụ được thực thi ra sao.

## Xác định thuộc tính theo phiên bản

Ở các phiên bản Spring Shell có hỗ trợ thuộc tính cấu hình chế độ tương tác, khóa thường dùng là:

```properties
spring.shell.interactive.enabled=true
```

Giá trị `true` biểu thị ứng dụng được phép khởi chạy vòng lặp tương tác; `false` tắt chế độ đó. Trước khi sử dụng, cần kiểm tra khóa này có được phiên bản thực tế của dự án hỗ trợ hay không. Không nên giả định mọi phiên bản Spring Shell đều có cùng khóa, cùng giá trị mặc định hoặc cùng cách xử lý tham số command line.

Hãy xác minh phiên bản theo thứ tự sau:

1. Kiểm tra dependency đã được resolve, kể cả phiên bản Spring Shell được quản lý gián tiếp qua Spring Boot BOM hoặc dependency management.
2. Mở tài liệu cấu hình của đúng release Spring Shell đó và tìm phần interactive mode hoặc application properties.
3. Kiểm tra metadata cấu hình mà dependency cung cấp, chẳng hạn `META-INF/spring-configuration-metadata.json`, hoặc dùng gợi ý cấu hình của IDE.
4. Chạy ứng dụng với cấu hình dự kiến để xác nhận prompt có xuất hiện hay không và tiến trình có chờ nhập lệnh hay không.

Một thuộc tính viết đúng cú pháp trong `application.yml` vẫn có thể không tạo ra hiệu lực nếu phiên bản hiện tại không hỗ trợ khóa đó. Vì vậy, việc ứng dụng khởi động thành công chưa đủ để chứng minh chế độ đã được cấu hình đúng.

## Khai báo rõ chế độ trong cấu hình ứng dụng

Với phiên bản hỗ trợ `spring.shell.interactive.enabled`, có thể khai báo chế độ tương tác trong `application.yml`:

```yaml
spring:
  shell:
    interactive:
      enabled: true
```

Cấu hình này thể hiện ứng dụng được dùng như một terminal tương tác. Khi chạy trong môi trường tự động, có thể tắt chế độ tương tác bằng cấu hình riêng:

```yaml
spring:
  shell:
    interactive:
      enabled: false
```

Nếu dự án cần cả hai kiểu chạy, hãy đặt cấu hình theo profile để mỗi môi trường có một lựa chọn dễ nhận biết. Ví dụ, `application.yml` dành cho phát triển tương tác:

```yaml
spring:
  shell:
    interactive:
      enabled: true
```

Và `application-automation.yml` dành cho tiến trình tự động:

```yaml
spring:
  shell:
    interactive:
      enabled: false
```

Kích hoạt profile tương ứng khi khởi chạy:

```bash
# Chạy phiên terminal tương tác theo cấu hình mặc định
java -jar customer-cli.jar

# Chạy với cấu hình dành cho tự động hóa
java -jar customer-cli.jar --spring.profiles.active=automation
```

Profile chỉ chọn nguồn cấu hình. Với chế độ không tương tác, cách truyền command hoặc script vẫn phải tuân theo cơ chế khởi chạy mà phiên bản Spring Shell đang hỗ trợ.

## Ghi đè cấu hình theo môi trường

Spring Boot cho phép truyền thuộc tính cấu hình qua nhiều nguồn. Điều này hữu ích khi cùng một artifact được chạy ở máy phát triển và pipeline mà không cần đóng gói hai bản ứng dụng.

Có thể ghi đè thuộc tính khi khởi chạy:

```bash
java -jar customer-cli.jar --spring.shell.interactive.enabled=false
```

Hoặc dùng biến môi trường trong container hay pipeline:

```bash
SPRING_SHELL_INTERACTIVE_ENABLED=false
```

Trong PowerShell, có thể đặt biến môi trường cho tiến trình hiện tại trước khi chạy ứng dụng:

```powershell
$env:SPRING_SHELL_INTERACTIVE_ENABLED = "false"
java -jar customer-cli.jar
```

Thông thường, thuộc tính dòng lệnh có độ ưu tiên cao hơn cấu hình trong file; biến môi trường cũng có thể ghi đè cấu hình file theo cơ chế property source của Spring Boot. Khi điều tra một ứng dụng có nhiều nguồn cấu hình, hãy kiểm tra profile đang hoạt động và giá trị cuối cùng được bind thay vì chỉ nhìn một file `application.yml`.

Không nên đặt giá trị trái ngược ở nhiều nguồn mà không có chủ ý. Chẳng hạn, file cấu hình bật interactive nhưng biến môi trường của container lại tắt có thể khiến người vận hành hiểu nhầm khi chạy trực tiếp trên máy. Hãy ghi rõ nguồn nào quyết định chế độ ở từng môi trường.

## Chọn chế độ phù hợp với cách khởi chạy

| Tình huống | Chế độ thường phù hợp | Điều cần xác nhận |
| --- | --- | --- |
| Nhân viên mở terminal và nhập nhiều lệnh | Tương tác | Prompt, trợ giúp, tự hoàn thành và cách thoát phiên |
| Nhà phát triển thử command thủ công | Tương tác | Cấu hình môi trường phát triển có bật chế độ tương tác |
| Pipeline gọi một command rồi thu kết quả | Không tương tác | Command được truyền đúng cú pháp và tiến trình kết thúc |
| Cron hoặc container job chạy định kỳ | Không tương tác | Không chờ TTY, log có thể đọc và mã thoát chính xác |
| Script thực hiện nhiều thao tác liên tiếp | Theo cơ chế script của phiên bản | Script được bật và xử lý lỗi theo đúng tài liệu release |

Đặc biệt, không đồng nhất chế độ tương tác với khả năng chạy script. Một ứng dụng có thể tắt prompt nhưng vẫn cần cơ chế script được hỗ trợ riêng. Tương tự, bật chế độ tương tác không tự động làm cho mọi command có trợ giúp hoặc tự hoàn thành; những khả năng đó còn phụ thuộc khai báo command và cấu hình liên quan.

## Ví dụ tổ chức cấu hình cho hai môi trường

Giả sử `customer-cli` được dùng bởi nhân viên hỗ trợ và một pipeline triển khai. Hai môi trường có yêu cầu khác nhau:

- Nhân viên hỗ trợ chạy ứng dụng tại máy làm việc, nhập `customer list`, sau đó nhập `customer show` và nhiều command khác. Ứng dụng cần giữ phiên terminal mở.
- Pipeline gọi command kiểm tra khách hàng sau khi triển khai. Job cần nhận kết quả, kiểm tra mã thoát và kết thúc để pipeline chuyển sang bước kế tiếp.

Có thể tổ chức cấu hình theo profile như sau:

```text
src/main/resources/
  application.yml
  application-automation.yml
```

`application.yml`:

```yaml
spring:
  shell:
    interactive:
      enabled: true
```

`application-automation.yml`:

```yaml
spring:
  shell:
    interactive:
      enabled: false
```

Nhân viên chạy artifact với cấu hình mặc định. Pipeline kích hoạt profile `automation` và truyền command theo cách gọi không tương tác của phiên bản dự án. Khi xem log, cả hai môi trường nên thể hiện rõ cấu hình đã chọn để người vận hành dễ xác định vì sao ứng dụng hiển thị prompt hoặc kết thúc sau một lần thực thi.

Trong triển khai thực tế, tránh ghi thông tin nhạy cảm vào command line hoặc log. Cấu hình chế độ tương tác không phải nơi lưu credential; thông tin xác thực nên được cấp qua cơ chế quản lý secret phù hợp với môi trường.

## Kiểm thử hành vi khởi chạy

Kiểm tra giá trị cấu hình trong ApplicationContext là cần thiết nhưng chưa đủ. Cần xác minh hành vi của tiến trình ở cả hai chế độ, vì mục tiêu là kiểm soát việc ứng dụng có mở vòng lặp chờ nhập lệnh hay không.

| Trường hợp | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Bật tương tác | Khởi chạy trong terminal có TTY | Prompt xuất hiện và nhận được nhiều command trong cùng phiên |
| Tắt tương tác | Khởi chạy với thuộc tính false | Không mở vòng lặp prompt tương tác |
| Gọi command tự động | Truyền command theo cú pháp của phiên bản | Command được thực thi và tiến trình kết thúc |
| Thiếu đầu vào cần thiết | Gọi command với option bắt buộc bị thiếu | Lỗi được báo rõ và mã thoát phản ánh thất bại |
| Môi trường không có TTY | Chạy trong pipeline hoặc terminal giả lập | Tiến trình không chờ nhập liệu ngoài dự kiến |
| Ghi đè cấu hình | Đặt thuộc tính qua profile, biến môi trường hoặc dòng lệnh | Giá trị cuối cùng đúng theo nguồn cấu hình có ưu tiên cao hơn |

Khi kiểm thử tự động, nên chạy ứng dụng như một tiến trình con với timeout. Nếu cấu hình vô tình bật prompt trong môi trường không tương tác, timeout giúp phát hiện job bị treo thay vì để bộ kiểm thử chờ vô hạn. Với kiểm thử tương tác, cấp đầu vào terminal giả lập hoặc TTY phù hợp để xác minh vòng lặp nhận lệnh và cách thoát.

Hãy kiểm tra cả mã thoát. Một command in thông báo lỗi nhưng kết thúc với mã `0` có thể khiến pipeline đánh dấu thành công. Ngược lại, một command thành công cần trả mã thoát thành công để script có thể tiếp tục đúng luồng.

## Những nhầm lẫn thường gặp

| Nhầm lẫn | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Cho rằng giá trị mặc định giống nhau ở mọi phiên bản | Nâng cấp dependency có thể làm thay đổi hành vi khởi chạy | Tra cứu tài liệu đúng release và khai báo tường minh |
| Thêm thuộc tính nhưng không xác minh phiên bản hỗ trợ | Cấu hình có thể không có hiệu lực | Kiểm tra configuration metadata và hành vi thực tế |
| Dùng cấu hình interactive cho mục đích bật/tắt script | Script có thể vẫn không được hỗ trợ như mong đợi | Kiểm tra cấu hình script riêng của phiên bản |
| Chạy ứng dụng tương tác trong CI không có TTY | Job có thể chờ nhập lệnh | Tắt interactive trong profile tự động hóa |
| Chỉ kiểm tra file YAML mà không kiểm tra nguồn ghi đè | Giá trị lúc chạy khác điều người phát triển dự đoán | Kiểm tra profile, biến môi trường và tham số dòng lệnh |
| Chỉ kiểm tra prompt mà bỏ qua mã thoát | Pipeline không phát hiện command thất bại | Kiểm thử kết quả và mã thoát của tiến trình |

## Quy trình cấu hình trước khi phát hành

1. Xác định ứng dụng được dùng chủ yếu như terminal tương tác, command một lần hay cả hai.
2. Xác nhận phiên bản Spring Shell thực tế và thuộc tính tương ứng trong tài liệu của release đó.
3. Khai báo rõ chế độ trong file cấu hình hoặc profile của từng môi trường.
4. Xác định cách truyền command hoặc script cho chế độ không tương tác theo phiên bản.
5. Kiểm thử prompt, khả năng nhận command, hành vi kết thúc và mã thoát.
6. Ghi lại nguồn cấu hình có quyền ghi đè để người vận hành có thể chẩn đoán khi hành vi khởi chạy khác dự kiến.

Cấu hình chế độ tương tác một cách tường minh giúp ứng dụng Spring Shell khởi chạy đúng với môi trường sử dụng. Khi giá trị mặc định của framework thay đổi theo phiên bản, cấu hình và kiểm thử rõ ràng giữ cho trải nghiệm terminal cũng như quy trình tự động hóa có thể dự đoán được.
