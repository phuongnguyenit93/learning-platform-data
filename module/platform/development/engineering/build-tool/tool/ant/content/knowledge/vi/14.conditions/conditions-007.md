# Thu thập tham số bằng input và thiết kế chế độ không tương tác

Một build Ant đôi khi cần người chạy cung cấp thông tin trước khi thực hiện công việc: chọn môi trường triển khai, chọn biến thể đóng gói, xác nhận một thao tác hoặc nhập đường dẫn đầu vào. Với người chạy Ant trực tiếp trong terminal, task input có thể hiển thị câu hỏi và nhận câu trả lời. Nhưng khi build chạy trong CI, script theo lịch hoặc máy chủ không có người tương tác, việc chờ nhập liệu có thể khiến job bị treo hoặc thất bại.

Thiết kế tốt cần phân biệt hai cách vận hành:

- **Chế độ tương tác:** hỏi người dùng khi thật sự cần một quyết định hoặc giá trị.
- **Chế độ không tương tác:** nhận tất cả tham số từ dòng lệnh, property file hoặc cấu hình môi trường; xác thực chúng trước khi chạy các bước quan trọng.

Ant hỗ trợ task input để thu thập dữ liệu và các cơ chế property, condition, fail, if/unless để kiểm tra và điều khiển luồng build. Khi kết hợp đúng, cùng một build file có thể phục vụ cả máy phát triển lẫn pipeline tự động.

## 1. Thu thập dữ liệu từ terminal bằng task input

### 1.1. Cú pháp cơ bản

Task input hiển thị một thông điệp và lưu câu trả lời vào một property:

~~~xml
<target name="choose-environment">
    <input message="Nhap moi truong (dev/staging/prod):"
           addproperty="deploy.environment" />
    <echo message="Selected environment: ${deploy.environment}" />
</target>
~~~

Khi chạy target trong terminal tương tác:

~~~text
ant choose-environment
~~~

Ant hiển thị câu hỏi, chờ người chạy nhập giá trị rồi gán giá trị đó cho property deploy.environment. Target tiếp theo có thể dùng property này để chọn cấu hình hoặc quyết định bước build.

Các thuộc tính chính của task input:

| Thuộc tính | Ý nghĩa |
|---|---|
| message | Nội dung câu hỏi hiển thị cho người chạy |
| addproperty | Tên property nhận câu trả lời |
| validargs | Danh sách các giá trị được phép, phân tách bằng dấu phẩy |

Tên property nên mô tả rõ dữ liệu cần nhận, chẳng hạn deploy.environment, package.variant hoặc test.profile. Tránh tên quá chung như answer hoặc value khi build có nhiều câu hỏi.

### 1.2. Giới hạn câu trả lời bằng validargs

Nếu câu trả lời chỉ được phép nằm trong một tập giá trị, hãy khai báo validargs:

~~~xml
<target name="choose-environment">
    <input message="Chon moi truong (dev/staging/prod):"
           addproperty="deploy.environment"
           validargs="dev,staging,prod" />
</target>
~~~

Người chạy chỉ được nhập một trong ba giá trị dev, staging hoặc prod. Nếu nhập giá trị ngoài danh sách, input handler có thể yêu cầu nhập lại hoặc xử lý theo chính sách của handler đang dùng.

validargs hữu ích cho lựa chọn có phạm vi đóng như môi trường, loại gói hoặc chế độ kiểm thử. Với dữ liệu tự do như đường dẫn hoặc chuỗi phiên bản, cần kiểm tra thêm sau khi nhận được giá trị; không nên coi việc nhập được một chuỗi là bằng chứng chuỗi đó hợp lệ.

### 1.3. Property đã có thì input không hỏi lại

Ant property có tính bất biến: sau khi một property đã được thiết lập, các lần thiết lập thông thường tiếp theo không ghi đè giá trị đó. Task input cũng kiểm tra property đích; nếu property đã có giá trị, task không cần hỏi lại người dùng.

Ví dụ, build file có thể nhận giá trị từ dòng lệnh:

~~~text
ant -Ddeploy.environment=staging choose-environment
~~~

Khi target choose-environment chạy, property deploy.environment đã tồn tại, nên input không cần mở prompt. Cùng một target có thể dùng ở terminal và trong script nếu giá trị được cung cấp trước khi task input chạy.

Đặc tính này rất hữu ích để tái sử dụng build file, nhưng cũng cần hiểu rõ: nếu đặt property mặc định trước task input, prompt sẽ bị bỏ qua.

~~~xml
<property name="deploy.environment" value="dev" />

<target name="choose-environment">
    <input message="Chon moi truong:"
           addproperty="deploy.environment"
           validargs="dev,staging,prod" />
</target>
~~~

Trong ví dụ trên, property đã được đặt thành dev ở cấp project. Task input sẽ không hỏi người dùng. Nếu mục tiêu là luôn hỏi trong chế độ tương tác, đừng thiết lập property mặc định trước task input đó. Nếu mục tiêu là chạy tự động với giá trị mặc định an toàn, hãy thiết kế riêng quy tắc mặc định và xác thực.

## 2. Tổ chức tham số thành property

### 2.1. Truyền giá trị qua dòng lệnh với -D

Tùy chọn -Dname=value truyền một property cho Ant ngay khi khởi chạy:

~~~text
ant -Ddeploy.environment=staging deploy
~~~

Trong build file, property có thể được sử dụng bằng cú pháp nội suy:

~~~xml
<target name="deploy">
    <echo message="Deploy environment: ${deploy.environment}" />
    <!-- Các task triển khai dùng cấu hình đã chọn -->
</target>
~~~

Có thể truyền nhiều property cùng lúc:

~~~text
ant -Ddeploy.environment=staging -Dpackage.variant=full -Dskip.tests=false package
~~~

Cách này phù hợp với CI vì pipeline có thể cung cấp tham số rõ ràng mà không cần người vận hành nhập trực tiếp vào tiến trình Ant.

Nếu giá trị chứa dấu cách hoặc ký tự đặc biệt, cách quote phụ thuộc shell đang sử dụng. Hãy quote giá trị theo cú pháp của PowerShell, cmd.exe, Bash hoặc shell tương ứng. Không đưa mật khẩu hoặc token vào dòng lệnh vì chúng có thể xuất hiện trong lịch sử shell, danh sách tiến trình hoặc log của pipeline.

### 2.2. Nạp cấu hình từ property file

Khi có nhiều tham số, có thể lưu chúng trong tệp properties:

~~~properties
deploy.environment=staging
package.variant=full
test.profile=integration
~~~

Nạp tệp bằng tùy chọn dòng lệnh:

~~~text
ant -propertyfile config/ci.properties deploy
~~~

Hoặc nạp từ bên trong build file:

~~~xml
<property file="config/build.properties" />
~~~

Property file hữu ích khi một nhóm tham số thường được dùng cùng nhau, ví dụ cấu hình local, staging hoặc CI. Nên quản lý các file cấu hình mẫu trong repository và cung cấp giá trị thật từ hệ thống triển khai hoặc secret store.

Property file không nên chứa secret ở dạng văn bản thuần được commit vào repository. Với thông tin xác thực, dùng cơ chế quản lý bí mật của CI hoặc nền tảng triển khai; chỉ truyền giá trị vào tiến trình build theo cách đã được tổ chức kiểm soát.

### 2.3. Lấy dữ liệu từ biến môi trường

Ant có thể đưa biến môi trường vào property bằng thuộc tính environment:

~~~xml
<property environment="env" />
~~~

Sau đó, biến môi trường DEPLOY_ENV có thể được tham chiếu bằng:

~~~xml
<echo message="Environment from OS: ${env.DEPLOY_ENV}" />
~~~

Ví dụ trong shell Linux/macOS:

~~~bash
export DEPLOY_ENV=staging
ant -noinput deploy
~~~

Ví dụ trong PowerShell:

~~~powershell
$env:DEPLOY_ENV = "staging"
ant -noinput deploy
~~~

Việc nạp biến môi trường không tự động gán DEPLOY_ENV vào property deploy.environment. Nếu build cần một tên property thống nhất, hãy ánh xạ có chủ đích và kiểm tra trường hợp biến môi trường chưa được thiết lập. Không nên âm thầm dùng giá trị rỗng cho một thao tác quan trọng.

## 3. Xác thực tham số trước khi thực hiện target

### 3.1. Kiểm tra property bắt buộc

Một target triển khai cần biết môi trường đích. Nếu property không có, build nên dừng với thông báo cụ thể:

~~~xml
<target name="validate-deploy-parameters">
    <fail unless="deploy.environment"
          message="Missing required property: deploy.environment" />
</target>

<target name="deploy" depends="validate-deploy-parameters">
    <echo message="Deploying to ${deploy.environment}" />
    <!-- Các task triển khai -->
</target>
~~~

Khi gọi deploy mà không cung cấp deploy.environment, target xác thực dừng build trước khi chạy thao tác triển khai.

Đây là cách phù hợp với chế độ không tương tác: thay vì đợi người dùng trả lời, build yêu cầu tham số phải có sẵn và báo lỗi ngay nếu thiếu.

### 3.2. Kiểm tra giá trị thuộc danh sách cho phép

Việc property tồn tại chưa bảo đảm giá trị đúng. Ví dụ, deploy.environment có thể là một chuỗi bất kỳ do người gọi truyền vào. Dùng condition để tạo property đánh dấu giá trị hợp lệ:

~~~xml
<target name="validate-deploy-parameters">
    <condition property="deploy.environment.valid">
        <or>
            <equals arg1="${deploy.environment}" arg2="dev" />
            <equals arg1="${deploy.environment}" arg2="staging" />
            <equals arg1="${deploy.environment}" arg2="prod" />
        </or>
    </condition>

    <fail unless="deploy.environment.valid"
          message="deploy.environment must be dev, staging or prod" />
</target>
~~~

Nếu giá trị không thuộc danh sách, property deploy.environment.valid không được tạo và task fail dừng build.

Khi so sánh chuỗi, cần thống nhất chữ hoa/chữ thường. Ví dụ staging và STAGING có thể không được coi là cùng một giá trị nếu không có bước chuẩn hóa. Hãy quy định cách viết được chấp nhận và áp dụng nhất quán trong property file, pipeline và build file.

### 3.3. Kết hợp kiểm tra bắt buộc và kiểm tra miền giá trị

Có thể viết target xác thực theo thứ tự để thông báo lỗi dễ hiểu:

~~~xml
<target name="validate-deploy-parameters">
    <fail unless="deploy.environment"
          message="Please provide -Ddeploy.environment=dev|staging|prod" />

    <condition property="deploy.environment.valid">
        <or>
            <equals arg1="${deploy.environment}" arg2="dev" />
            <equals arg1="${deploy.environment}" arg2="staging" />
            <equals arg1="${deploy.environment}" arg2="prod" />
        </or>
    </condition>

    <fail unless="deploy.environment.valid"
          message="Unsupported deploy.environment: ${deploy.environment}" />
</target>
~~~

Ở đây, lỗi thiếu property được báo trước. Nếu property có nhưng giá trị không hợp lệ, thông báo thứ hai cho biết giá trị nhận được.

Trong ví dụ thực tế, có thể thêm các điều kiện khác như package.variant, release.version hoặc đường dẫn thư mục đầu vào. Nên tách thông báo theo từng tham số để người gọi biết cần sửa cấu hình nào.

## 4. Hiểu đúng điều kiện if và unless của target

Ant cho phép target chỉ chạy khi một property được thiết lập hoặc chưa được thiết lập:

~~~xml
<target name="production-only" if="is.production">
    <echo message="Production-specific task" />
</target>

<target name="non-production-only" unless="is.production">
    <echo message="Non-production task" />
</target>
~~~

Điểm dễ nhầm là if và unless của target kiểm tra sự tồn tại của property, không đánh giá nội dung chuỗi thành true/false theo cách thông thường.

Ví dụ:

~~~xml
<property name="is.production" value="false" />

<target name="production-only" if="is.production">
    <echo message="This target still runs because the property exists" />
</target>
~~~

Property is.production đã được thiết lập, dù giá trị chuỗi là false. Vì vậy target production-only vẫn chạy.

Muốn kiểm tra một giá trị cụ thể, hãy tạo property điều kiện bằng task condition. Nếu giá trị có thể được nhập bởi một target chạy trước đó, hãy đặt condition bên trong target xác thực để nó được đánh giá sau khi người dùng đã nhập:

~~~xml
<target name="validate-deploy-environment">
    <condition property="is.production">
        <equals arg1="${deploy.environment}" arg2="prod" />
    </condition>
</target>
~~~

Property is.production chỉ được tạo khi điều kiện so sánh đúng. Sau đó, target if/unless có thể dựa vào sự tồn tại của property này.

## 5. Thiết kế hai luồng tương tác và không tương tác

Một thiết kế dễ hiểu là tách target thu thập dữ liệu khỏi target xác thực và target thực hiện công việc.

~~~xml
<project name="deployment" default="deploy" basedir=".">

    <target name="prompt-deploy-environment">
        <input message="Chon moi truong (dev/staging/prod):"
               addproperty="deploy.environment"
               validargs="dev,staging,prod" />
    </target>

    <target name="validate-deploy-environment">
        <fail unless="deploy.environment"
              message="Missing deploy.environment" />

        <condition property="deploy.environment.valid">
            <or>
                <equals arg1="${deploy.environment}" arg2="dev" />
                <equals arg1="${deploy.environment}" arg2="staging" />
                <equals arg1="${deploy.environment}" arg2="prod" />
            </or>
        </condition>

        <fail unless="deploy.environment.valid"
              message="Unsupported deploy.environment: ${deploy.environment}" />
    </target>

    <target name="deploy" depends="validate-deploy-environment">
        <echo message="Deploying to ${deploy.environment}" />
        <!-- Các task triển khai -->
    </target>

</project>
~~~

Chạy tương tác:

~~~text
ant prompt-deploy-environment deploy
~~~

Ant chạy target prompt-deploy-environment trước, nhận giá trị từ terminal rồi tiếp tục target deploy. Vì cả hai target nằm trong cùng một lần chạy Ant, property đã nhập được dùng trong bước xác thực và triển khai.

Chạy không tương tác:

~~~text
ant -noinput -Ddeploy.environment=staging deploy
~~~

Property đã được cung cấp trước khi build chạy. Target deploy không cần gọi prompt; target validate-deploy-environment kiểm tra giá trị trước khi thực hiện.

Cấu trúc này có một ưu điểm quan trọng: target deploy luôn yêu cầu tham số hợp lệ, còn việc lấy tham số từ terminal hay pipeline được quyết định ở cách gọi. Nếu có một giá trị mặc định được khai báo ở cấp project, task input sẽ thấy property đã tồn tại và bỏ qua prompt; vì vậy hãy cân nhắc kỹ trước khi thêm default cho tham số triển khai.

## 6. Thiết kế chế độ không tương tác cho CI

### 6.1. Dùng -noinput khi chạy tự động

Tùy chọn dòng lệnh:

~~~text
ant -noinput deploy
~~~

yêu cầu Ant không chờ nhập liệu tương tác. Đây là lựa chọn phù hợp cho CI, cron job và script tự động.

Tuy nhiên, -noinput không tự tạo giá trị cho các property còn thiếu. Build vẫn cần nhận dữ liệu qua -D, property file, biến môi trường hoặc cấu hình mặc định đã được thiết kế. Nếu một task input vẫn cần câu trả lời mà không có nguồn dữ liệu phù hợp, build có thể không thực hiện được yêu cầu đó và phải dừng.

Không nên dựa vào việc CI sẽ tự gửi phím Enter hoặc câu trả lời mặc định. Điều đó làm build phụ thuộc vào terminal và có thể chọn nhầm môi trường hoặc cấu hình.

### 6.2. Cung cấp property trước khi gọi Ant

Ví dụ dùng property file:

~~~text
ant -noinput -propertyfile config/ci.properties deploy
~~~

Hoặc truyền trực tiếp các tham số không nhạy cảm:

~~~text
ant -noinput -Ddeploy.environment=staging -Dpackage.variant=full deploy
~~~

Trong pipeline, các giá trị có thể được lấy từ cấu hình job, biến môi trường hoặc bước phê duyệt trước đó. Build file chỉ nên xác thực rằng chúng đã có và nằm trong miền giá trị được phép.

### 6.3. Dùng input handler khi thật sự cần cơ chế nhập riêng

Ant hỗ trợ tùy chọn dòng lệnh -inputhandler để chỉ định lớp xử lý các yêu cầu nhập liệu. Cơ chế này dành cho trường hợp dự án cần một input handler tùy chỉnh, chẳng hạn đọc dữ liệu từ nguồn đã được kiểm soát hoặc tích hợp với hệ thống vận hành riêng.

Đối với phần lớn pipeline, cách đơn giản và dễ kiểm soát hơn là truyền đủ property trước khi chạy Ant và bật -noinput. Chỉ triển khai input handler riêng khi có yêu cầu rõ ràng về cách thu thập và xác thực dữ liệu.

## 7. Chọn giá trị mặc định một cách có chủ đích

Không phải tham số nào cũng cần bắt buộc. Một số tùy chọn có thể có mặc định hợp lý, ví dụ package.variant=standard hoặc test.profile=unit.

Có thể khai báo property mặc định:

~~~xml
<property name="package.variant" value="standard" />
~~~

Người gọi vẫn có thể truyền giá trị khác:

~~~text
ant -Dpackage.variant=full package
~~~

Property được truyền từ dòng lệnh là user property và đã có trước khi build file khai báo default. Vì property của Ant không bị ghi đè bởi các lần khai báo thông thường sau đó, giá trị dòng lệnh sẽ được giữ.

Với tham số có ảnh hưởng lớn như môi trường triển khai, tài khoản đích hoặc thao tác xóa dữ liệu, không nên chọn mặc định nguy hiểm. Có thể yêu cầu người gọi truyền rõ ràng và dùng fail nếu thiếu.

Một nguyên tắc thực tế:

| Loại tham số | Cách xử lý gợi ý |
|---|---|
| Tùy chọn build ít rủi ro | Có thể cung cấp default rõ ràng |
| Môi trường chạy ứng dụng | Dùng default cho local nếu phù hợp; CI truyền rõ |
| Môi trường triển khai | Yêu cầu truyền rõ và xác thực danh sách cho phép |
| Đường dẫn đầu vào quan trọng | Kiểm tra tồn tại và loại đường dẫn trước khi chạy |
| Xác nhận thao tác phá hủy | Yêu cầu xác nhận rõ trong chế độ tương tác; chế độ CI dùng điều kiện phê duyệt riêng |
| Mật khẩu hoặc token | Lấy từ secret store/CI secret; không lưu trong build file hoặc log |

## 8. Xác thực đường dẫn và tham số dạng chuỗi

Không phải mọi tham số đều là một lựa chọn đơn giản. Build có thể cần nhận thư mục nguồn, đường dẫn artifact hoặc phiên bản phát hành.

Ví dụ kiểm tra một thư mục đầu vào:

~~~xml
<target name="validate-input-directory">
    <fail unless="input.dir"
          message="Missing required property: input.dir" />

    <available file="${input.dir}"
               type="dir"
               property="input.dir.exists" />

    <fail unless="input.dir.exists"
          message="input.dir must point to an existing directory" />
</target>
~~~

Task available kiểm tra sự tồn tại và loại của đường dẫn, sau đó tạo property input.dir.exists nếu điều kiện đúng.

Nếu tham số là tệp, dùng type="file". Nếu đường dẫn phải nằm trong một thư mục gốc được phép, cần kiểm tra thêm đường dẫn đã chuẩn hóa và quan hệ của nó với thư mục gốc đó. Chỉ kiểm tra tệp có tồn tại không đủ để chứng minh đường dẫn thuộc phạm vi dự án.

Với chuỗi phiên bản, có thể kiểm tra theo quy ước đặt tên mà dự án chấp nhận. Không nên ghép chuỗi đầu vào trực tiếp vào đường dẫn hoặc lệnh hệ thống nếu chưa xác thực; ký tự đặc biệt có thể làm thay đổi cách shell hoặc task diễn giải tham số.

## 9. Xử lý xác nhận thao tác quan trọng

Một số target có tác động đáng kể như triển khai production, xóa dữ liệu hoặc ghi đè artifact. Trong chế độ tương tác, có thể yêu cầu người dùng xác nhận:

~~~xml
<target name="confirm-production-deploy">
    <input message="Deploy to production? Enter yes or no:"
           addproperty="confirm.production"
           validargs="yes,no" />

    <fail unless="confirm.production"
          message="Production confirmation is required" />

    <condition property="production.confirmed">
        <equals arg1="${confirm.production}" arg2="yes" />
    </condition>

    <fail unless="production.confirmed"
          message="Production deployment was not confirmed" />
</target>
~~~

Trong CI, không nên trông chờ prompt này. Pipeline nên có bước phê duyệt hoặc điều kiện bảo vệ môi trường trước khi gọi target triển khai. Sau khi được phê duyệt, job truyền một property xác nhận rõ ràng:

~~~text
ant -noinput -Dconfirm.production=yes -Ddeploy.environment=prod deploy-production
~~~

Target triển khai phải kiểm tra cả xác nhận lẫn môi trường. Property xác nhận chỉ là dữ liệu đầu vào của build; nó không thay thế quyền phê duyệt và kiểm soát truy cập của hệ thống CI.

Đặc biệt, không thiết kế để thiếu xác nhận tự động chuyển thành yes. Khi thiếu thông tin, hãy dừng build với thông báo rõ ràng.

## 10. Bảo vệ thông tin nhạy cảm khi thu thập tham số

Task input thông thường không nên được xem là cơ chế nhập mật khẩu an toàn. Tùy input handler và terminal, nội dung người dùng nhập có thể hiển thị hoặc bị ghi lại. Tương tự, giá trị truyền qua -D có thể lộ trong lịch sử lệnh, danh sách tiến trình, log hoặc báo cáo lỗi.

Với password, API key và access token:

- Lấy giá trị từ secret store hoặc cơ chế secret của CI.
- Không commit secret vào property file.
- Không echo giá trị bí mật trong build file.
- Tránh truyền secret trực tiếp trên dòng lệnh nếu môi trường có thể ghi lại command line.
- Không bật log chi tiết nếu nó có thể làm lộ giá trị.
- Chỉ truyền secret tới task thực sự cần nó và giữ phạm vi sử dụng ngắn nhất có thể.
- Nếu bắt buộc phải nhập tương tác, dùng input handler chuyên biệt có khả năng xử lý dữ liệu nhạy cảm theo chính sách của dự án.

Có thể log tên môi trường hoặc mã job để truy vết mà không in token hoặc mật khẩu. Ví dụ, log "Deploying to staging" hữu ích hơn việc in toàn bộ cấu hình xác thực.

## 11. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể xảy ra | Hướng xử lý |
|---|---|---|
| Build chờ nhập liệu trong CI | Target vẫn gọi input nhưng property chưa được cung cấp | Truyền property trước khi chạy và dùng -noinput |
| Task input không hiển thị prompt | Property addproperty đã tồn tại | Kiểm tra property được thiết lập ở dòng lệnh, property file hoặc cấp project |
| Giá trị nhập bị từ chối | validargs không chứa giá trị hoặc khác chữ hoa/chữ thường | Chuẩn hóa tập giá trị và cách viết |
| Build chạy với môi trường sai | Property mặc định hoặc giá trị pipeline không như mong đợi | In tên môi trường đã chọn và xác thực miền giá trị trước deploy |
| if="flag" vẫn chạy khi flag=false | Target kiểm tra sự tồn tại của property, không kiểm tra chuỗi boolean | Tạo property điều kiện bằng condition |
| Build không dừng khi thiếu property | Không có target xác thực hoặc target sử dụng không phụ thuộc vào target xác thực | Thêm fail và depends trước công việc chính |
| Giá trị từ property file không được dùng | Property đã được thiết lập trước đó hoặc đường dẫn file cấu hình sai | Kiểm tra thứ tự nạp và nguồn thiết lập property |
| Build tương tác hoạt động nhưng CI thất bại | Pipeline không có terminal hoặc thiếu tham số | Thiết kế luồng CI riêng, truyền đầy đủ property |
| Secret xuất hiện trong log | Build echo tham số hoặc bật log có nội dung nhạy cảm | Loại secret khỏi log và dùng secret store |
| Target triển khai production chạy ngoài ý muốn | Mặc định hoặc điều kiện xác nhận quá dễ dãi | Yêu cầu property rõ ràng, xác thực môi trường và dùng phê duyệt CI |

## 12. Quy trình mẫu cho một build có hai chế độ

Một quy trình có thể tổ chức theo các bước sau:

1. Nạp các cấu hình không nhạy cảm.
2. Thu thập tham số bằng input nếu chạy trong terminal tương tác.
3. Nhận tham số từ dòng lệnh hoặc property file nếu chạy tự động.
4. Kiểm tra property bắt buộc và miền giá trị.
5. Kiểm tra đường dẫn đầu vào và các điều kiện môi trường.
6. Chạy compile, test, package hoặc deploy sau khi xác thực thành công.
7. Ghi log các giá trị không nhạy cảm cần thiết để truy vết.

Ví dụ lệnh:

~~~text
# Chế độ tương tác
ant prompt-deploy-environment deploy

# Chế độ CI với property file
ant -noinput -propertyfile config/ci.properties deploy

# Chế độ CI truyền tham số trực tiếp
ant -noinput -Ddeploy.environment=staging deploy
~~~

Cả ba cách gọi đều dẫn tới target deploy có bước xác thực. Khác biệt chỉ nằm ở nguồn cung cấp property.

## 13. Nguyên tắc thiết kế

- Dùng input cho lựa chọn cần người chạy trả lời trong terminal.
- Dùng validargs khi câu trả lời thuộc một tập giá trị cố định.
- Hiểu rằng property đã tồn tại thì task input không hỏi lại.
- Dùng -D, property file hoặc biến môi trường cho chế độ tự động.
- Bật -noinput trong CI để tránh phụ thuộc vào prompt.
- Xác thực tham số bằng condition, available và fail trước thao tác chính.
- Hiểu if/unless của target kiểm tra sự tồn tại property, không diễn giải chuỗi false.
- Không dùng default nguy hiểm cho môi trường triển khai hoặc thao tác phá hủy.
- Không lưu hoặc in secret trong build file, dòng lệnh và log.
- Dùng cơ chế phê duyệt của CI cho thao tác production; property xác nhận chỉ là một đầu vào bổ sung.

Một build Ant được thiết kế tốt luôn biết mình cần những tham số nào, lấy chúng từ đâu và phải dừng khi dữ liệu không hợp lệ. Khi tách rõ bước thu thập, xác thực và thực thi, build có thể chạy ổn định trong terminal tương tác cũng như trong môi trường tự động không có người nhập liệu.

