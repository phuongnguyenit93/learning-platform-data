# Chạy container bằng tài khoản không có quyền root

## Mục tiêu và phạm vi

Trong chương **Đóng gói ứng dụng** của module **SPRING_CLOUD_KUBERNETES**, bài học này hướng dẫn đóng gói và triển khai một ứng dụng Spring bằng người dùng Linux có UID khác `0`. Kết quả cần đạt là ứng dụng vẫn đọc được cấu hình, nhận lưu lượng và cung cấp health probe, trong khi quyền ghi và quyền hệ điều hành được giới hạn rõ ràng.

Sau bài học, bạn có thể:

- Chọn UID/GID và thiết lập người dùng mặc định của image.
- Kết hợp Dockerfile với `securityContext` trong Kubernetes.
- Chuẩn bị quyền đọc JAR, ConfigMap, Secret và vùng ghi tạm cho JVM.
- Phân biệt lỗi quyền tệp với lỗi RBAC khi DiscoveryClient hoặc bộ đọc cấu hình gọi Kubernetes API.
- Xác minh quyền thực tế của tiến trình và xử lý lỗi mà không chuyển ứng dụng về root.

Các ví dụ dành cho **Linux container**, kể cả khi chạy Docker Desktop trên Windows. Chúng giả định ứng dụng tương thích Java 21, đã có executable JAR và có Spring Boot Actuator. Phiên bản Spring Boot, Spring Cloud và Spring Cloud Kubernetes phải thuộc bộ phiên bản tương thích của dự án; bài này không yêu cầu nâng phiên bản.

## 1. Tại sao ứng dụng Spring cần một người dùng riêng?

Một dịch vụ HTTP thường cần đọc mã ứng dụng, mở cổng và ghi dữ liệu tạm. Các công việc đó không đòi hỏi tiến trình mang UID `0`. Khi tiến trình bị khai thác, quyền của tiến trình quyết định phần nào tài nguyên mà mã tấn công có thể sử dụng.

Container có các cơ chế cô lập, nhưng vẫn dùng kernel của môi trường Linux chạy nó. Vì vậy, chạy bằng root trong container làm tăng quyền sẵn có bên trong container và có thể làm hậu quả của cấu hình mount hoặc lỗ hổng nghiêm trọng hơn. Chạy non-root là một lớp giảm quyền, cần đi cùng giới hạn capability, volume và quyền API.

Cần phân biệt hai lựa chọn:

- **Ứng dụng non-root:** tiến trình Java trong container chạy với UID khác `0`.
- **Docker rootless:** daemon và container được vận hành bằng cơ chế không cần root ở phía host.

Một máy dùng Docker theo cách thông thường vẫn có thể chạy ứng dụng non-root. Ngược lại, không suy ra UID của Java chỉ từ cách daemon được cài đặt.

Ví dụ mục tiêu của bài:

~~~text
Tiến trình Java: UID 10001, GID 10001
/app/application.jar: chỉ cần đọc
/etc/app-config/: chỉ cần đọc
/run/secrets/app/: chỉ cần đọc
/tmp/: được phép ghi dữ liệu tạm
Kubernetes API: chỉ truy cập nếu tính năng đang dùng thực sự cần
~~~

Đây là thiết kế quyền cho ứng dụng mẫu, không phải danh sách bắt buộc cho mọi hệ thống.

## 2. Ba lớp danh tính cần tách biệt

| Lớp | Ví dụ | Quyền được quyết định |
| --- | --- | --- |
| Người dùng Linux trong container | UID `10001`, GID `10001` | Quyền của tiến trình đối với tệp và tài nguyên Linux |
| Kubernetes ServiceAccount | `nonroot-demo` trong namespace `nonroot-lab` | Danh tính dùng để xác thực với Kubernetes API |
| Người dùng nghiệp vụ của ứng dụng | Khách hàng đã đăng nhập | Quyền thao tác API và dữ liệu nghiệp vụ |

Đổi `runAsUser` không cấp quyền đọc ConfigMap qua Kubernetes API. Cấp Role cho ServiceAccount cũng không làm Java đọc được một tệp Linux mà UID/GID hiện tại không có quyền đọc.

Kubernetes cung cấp danh tính ServiceAccount và có thể tự động mount thông tin xác thực vào Pod. Có thể tắt việc mount tự động bằng `automountServiceAccountToken: false` khi ứng dụng không gọi Kubernetes API. Tham khảo [Service Accounts của Kubernetes](https://kubernetes.io/docs/concepts/security/service-accounts/).

Trong module này, sự phân biệt trên áp dụng trực tiếp:

- DiscoveryClient dùng Kubernetes API phải có danh tính và RBAC phù hợp.
- Spring Cloud LoadBalancer không yêu cầu Java chạy root; quyền API phụ thuộc cách lấy danh sách instance.
- Đọc ConfigMap/Secret qua API khác với đọc tệp đã được Kubernetes mount.
- Configuration Watcher là workload riêng nếu bạn triển khai nó riêng; cần xét UID, volume và RBAC của chính workload đó.

## 3. Thiết kế image với UID/GID cố định

### 3.1. Người dùng có tên và người dùng dạng số

Linux kiểm tra quyền bằng UID/GID. Tên `app` chủ yếu giúp con người đọc cấu hình và giúp một số thư viện tra cứu thông tin tài khoản.

Dùng `USER 10001:10001` làm giá trị mặc định giúp image thể hiện rõ UID và GID. Docker cho phép ghi đè người dùng lúc chạy, nên thiết lập trong image cần được kết hợp với chính sách khi triển khai. Ngữ nghĩa của `USER` được mô tả trong [Dockerfile reference](https://docs.docker.com/reference/dockerfile/#user).

UID `10001` chỉ là lựa chọn minh họa. Nếu nền tảng cấp một dải UID hoặc yêu cầu UID khác, hãy thiết kế quyền tệp theo chính sách đó. Không mặc định rằng mọi cluster đều chấp nhận UID cố định này.

### 3.2. Dockerfile mẫu

Giả sử bước build của dự án đã tạo ra executable JAR tại `target/application.jar`. Nếu dùng Gradle, thay giá trị `APP_JAR` bằng đúng đường dẫn artifact, chẳng hạn `build/libs/application.jar`. Không dùng wildcard có thể khớp cả JAR thường và executable JAR.

~~~dockerfile
# syntax=docker/dockerfile:1
FROM eclipse-temurin:21-jre-jammy

USER 0

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 \
       --no-create-home --home-dir /nonexistent \
       --shell /usr/sbin/nologin app \
    && mkdir -p /app \
    && chmod 0755 /app

WORKDIR /app

ARG APP_JAR=target/application.jar
COPY --chown=0:0 --chmod=0444 ${APP_JAR} /app/application.jar

USER 10001:10001

EXPOSE 8080
ENTRYPOINT ["java", "-Djava.io.tmpdir=/tmp", "-jar", "/app/application.jar"]
~~~

`groupadd` và `useradd` ở đây dành cho biến thể Ubuntu của base image. Nếu chọn Alpine, distroless hoặc base image khác, phải dùng cơ chế tạo người dùng tương ứng; không sao chép nguyên các lệnh hệ điều hành sang mọi image.

Trong ví dụ, root được dùng ở **giai đoạn build** để chuẩn bị tài khoản và tệp. Tiến trình Java lúc chạy nhận `USER 10001:10001`. Với multi-stage build, cần kiểm tra riêng stage cuối vì người dùng của stage build không tự động trở thành người dùng của một stage runtime độc lập.

JAR thuộc `root:root` với mode `0444` vì Java chỉ cần đọc nó. Thư mục `/app` có quyền `0755` để tiến trình đi vào và đọc tệp. Ứng dụng không cần sở hữu hoặc sửa mã của chính nó. `EXPOSE` chỉ mô tả cổng dự kiến; nó không mở cổng trên host.

Tag base image trong bài giúp ví dụ dễ đọc và có thể thay đổi theo thời gian. Khi phát hành, sử dụng digest đã được kiểm tra trong quy trình của dự án và duy trì lịch cập nhật base image.

### 3.3. Thử trước bằng Docker

Các lệnh dưới đây là thao tác thực hành dành cho người học, chạy ở thư mục có Dockerfile và artifact đã chuẩn bị:

~~~powershell
docker build --build-arg APP_JAR=target/application.jar -t nonroot-demo:nonroot .
docker image inspect nonroot-demo:nonroot --format '{{.Config.User}}'
~~~

Kết quả mong đợi của lệnh inspect là:

~~~text
10001:10001
~~~

Chạy ứng dụng trong một terminal:

~~~powershell
docker run --rm --name nonroot-demo --read-only --tmpfs /tmp:rw,nosuid,nodev,size=64m,mode=1777 --cap-drop ALL --security-opt no-new-privileges:true -p 127.0.0.1:8080:8080 -e MANAGEMENT_ENDPOINT_HEALTH_PROBES_ENABLED=true nonroot-demo:nonroot
~~~

Trong terminal khác:

~~~powershell
docker exec nonroot-demo id
docker exec nonroot-demo touch /tmp/nonroot-check
docker exec nonroot-demo rm /tmp/nonroot-check
docker exec nonroot-demo touch /app/should-fail
~~~

UID/GID phải là `10001`. Ghi trong `/tmp` phải thành công, còn ghi vào `/app` phải thất bại. Với `--read-only`, lỗi ở `/app` có thể là `Read-only file system`. Không dùng việc ghi thất bại làm bằng chứng duy nhất cho non-root: một tiến trình root cũng có thể gặp lỗi vì mount chỉ đọc.

Kiểm tra cả danh tính và quyền ghi giúp phát hiện hai lỗi khác nhau. Cú pháp ghi đè người dùng và các tùy chọn runtime được trình bày trong [Running containers của Docker](https://docs.docker.com/engine/containers/run/).

## 4. Chuyển yêu cầu quyền sang Kubernetes

Image đưa ra mặc định; manifest nêu rõ hợp đồng triển khai. Với Pod mẫu, cấu hình được chia như sau:

| Thiết lập | Vị trí trong ví dụ | Ý định |
| --- | --- | --- |
| `runAsNonRoot: true` | Pod | Yêu cầu container chạy bằng người dùng non-root |
| `runAsUser: 10001` | Pod | Chọn UID cụ thể |
| `runAsGroup: 10001` | Pod | Chọn GID chính |
| `fsGroup: 10001` | Pod | Cung cấp nhóm phục vụ truy cập volume có hỗ trợ |
| `seccompProfile: RuntimeDefault` | Pod | Dùng profile seccomp mặc định của runtime |
| `allowPrivilegeEscalation: false` | Container | Ngăn tiến trình con nhận thêm đặc quyền theo cơ chế nâng quyền |
| `capabilities.drop: [ALL]` | Container | Bỏ các Linux capability không cần cho ứng dụng mẫu |
| `readOnlyRootFilesystem: true` | Container | Chặn ghi lên root filesystem của container |

`runAsNonRoot` không tự tạo tài khoản hoặc chọn UID. Các trường trùng nhau ở cấp container có thể ghi đè thiết lập ở cấp Pod. `fsGroup` tác động theo loại volume và storage driver; nó không sửa quyền của JAR nằm trong image. Xem [hướng dẫn security context](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/).

Khi image chỉ khai báo tên người dùng, kubelet có thể không xác minh được người dùng đó có non-root hay không nếu thiếu UID rõ ràng. Dùng UID dạng số trong image và trong manifest của bài giúp tránh sự mơ hồ này.

Chính sách Pod Security mức Restricted còn kiểm tra nhiều yêu cầu ngoài UID. Cần xét cả init container, sidecar và container tạm, không chỉ container Java. `readOnlyRootFilesystem` là lớp bổ sung hữu ích nhưng không phải điều kiện bắt buộc của Restricted. Tham khảo [Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/).

## 5. Manifest thực hành hoàn chỉnh

### 5.1. Điều kiện của ứng dụng mẫu

JAR dùng cho ví dụ phải có web server và Spring Boot Actuator. Nếu có Spring Security, cho phép kubelet truy cập đúng các endpoint probe được dùng bên dưới theo thiết kế bảo mật của ứng dụng.

Bài thực hành này chọn **cấu hình qua tệp và kết nối dịch vụ qua DNS khi cần**, vì vậy không cần thư viện gọi Kubernetes API. Không thêm hoặc bật DiscoveryClient, bộ đọc cấu hình qua API hay watcher trong JAR chỉ để thực hành non-root. Nếu dự án sẵn có các thành phần đó, chọn profile vô hiệu hóa chúng theo đúng tài liệu của phiên bản đang dùng, hoặc chuyển sang phương án có ServiceAccount/RBAC ở mục 7.

Lưu nội dung sau thành một manifest trong môi trường thực hành. Secret chứa mật khẩu giả, chỉ phục vụ minh họa; không đưa thông tin xác thực thật vào tài liệu hoặc Git.

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: nonroot-lab
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: nonroot-demo
  namespace: nonroot-lab
automountServiceAccountToken: false
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: nonroot-demo-config
  namespace: nonroot-lab
data:
  application.yaml: |
    spring:
      application:
        name: nonroot-demo
      config:
        import: "configtree:/run/secrets/app/"
    server:
      port: 8080
    management:
      endpoints:
        web:
          exposure:
            include: health
      endpoint:
        health:
          probes:
            enabled: true
          show-details: never
    demo:
      message: "Ứng dụng đang chạy bằng người dùng non-root"
---
apiVersion: v1
kind: Secret
metadata:
  name: nonroot-demo-secret
  namespace: nonroot-lab
type: Opaque
stringData:
  demo.password: "lab-only-change-me"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nonroot-demo
  namespace: nonroot-lab
spec:
  replicas: 1
  selector:
    matchLabels:
      app: nonroot-demo
  template:
    metadata:
      labels:
        app: nonroot-demo
    spec:
      serviceAccountName: nonroot-demo
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: app
          image: nonroot-demo:nonroot
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: SPRING_CONFIG_ADDITIONAL_LOCATION
              value: "file:/etc/app-config/"
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
              ephemeral-storage: 128Mi
            limits:
              cpu: "1"
              memory: 512Mi
              ephemeral-storage: 512Mi
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
          volumeMounts:
            - name: tmp
              mountPath: /tmp
            - name: config
              mountPath: /etc/app-config
              readOnly: true
            - name: credentials
              mountPath: /run/secrets/app
              readOnly: true
      volumes:
        - name: tmp
          emptyDir:
            sizeLimit: 128Mi
        - name: config
          configMap:
            name: nonroot-demo-config
            defaultMode: 0444
        - name: credentials
          secret:
            secretName: nonroot-demo-secret
            defaultMode: 0440
---
apiVersion: v1
kind: Service
metadata:
  name: nonroot-demo
  namespace: nonroot-lab
spec:
  selector:
    app: nonroot-demo
  ports:
    - name: http
      port: 80
      targetPort: http
~~~

Trong lab, cluster phải tìm thấy image `nonroot-demo:nonroot`: nạp image vào node bằng cơ chế của cluster cục bộ hoặc đẩy lên registry rồi thay trường `image`. Build bằng Docker trên host không đảm bảo image tự xuất hiện trong mọi cluster.

Ở môi trường phát hành, thay tag lab bằng tên registry và digest cụ thể. Các con số CPU, RAM, dung lượng và thời gian probe là giá trị minh họa, cần điều chỉnh bằng dữ liệu của ứng dụng thực tế.

### 5.2. Giải thích luồng khởi động

1. Runtime khởi động Java bằng UID/GID `10001` theo manifest.
2. Spring Boot đọc `application.yaml` trong `/etc/app-config/` nhờ `SPRING_CONFIG_ADDITIONAL_LOCATION`.
3. Cấu hình `configtree:` ánh xạ tên tệp Secret `demo.password` thành property cùng tên. Ứng dụng nghiệp vụ chỉ dùng giá trị này khi có binding hoặc mã đọc property tương ứng.
4. JVM và thư viện có thể ghi dữ liệu tạm vào volume `/tmp`.
5. Các probe truy cập cổng `8080`; Service cung cấp cổng `80` và chuyển tiếp tới cổng ứng dụng.

Không có bước nào cần Java ghi vào `/app`, sửa `/etc` hoặc gọi Kubernetes API để đọc cấu hình đã mount.

Cổng `8080` giúp tránh phụ thuộc quyền bind cổng thấp của môi trường Linux. Quyền bind cổng dưới `1024` còn phụ thuộc capability và sysctl; không nên lấy việc bind cổng thấp thành công hay thất bại làm phép thử duy nhất cho root.

Spring Boot hỗ trợ health group riêng cho liveness/readiness. Trong thiết kế này, kiểm tra HTTP do kubelet thực hiện nên không cần cài `curl` vào image. Không đưa lỗi một dịch vụ phụ thuộc bên ngoài vào liveness một cách máy móc, vì việc khởi động lại mọi Pod có thể làm sự cố nặng hơn. Tham khảo [Kubernetes probes trong Spring Boot Actuator](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

## 6. Quyền ghi, volume và cấu hình

### 6.1. Root filesystem chỉ đọc vẫn cần vùng ghi được

`readOnlyRootFilesystem` không biến mọi volume thành chỉ đọc. Bài thực hành cố ý để `/tmp` ghi được và gắn ConfigMap/Secret ở chế độ đọc.

Hãy lập danh sách đường dẫn mà ứng dụng thực sự dùng:

| Nhu cầu | Cách xử lý phù hợp |
| --- | --- |
| File tạm của servlet container hoặc thư viện | Đặt trong `/tmp` hoặc một volume tạm riêng |
| Log vận hành thông thường | Ghi ra stdout/stderr |
| File upload cần tồn tại sau khi thay Pod | Dùng object storage hoặc volume bền vững theo thiết kế |
| Heap dump, JFR, cache ghi ra đĩa | Cấp volume riêng, giới hạn dung lượng và quyền truy cập |
| Java Preferences hoặc thư viện cần home directory | Cấu hình đường dẫn home/cache hợp lệ nếu ứng dụng sử dụng |
| Chứng thư được cập nhật động | Dùng cơ chế cung cấp truststore phù hợp; không sửa truststore hệ thống lúc chạy |

Dockerfile dùng home `/nonexistent` để tránh tạo thư mục không cần thiết. Nếu thư viện cần ghi dưới `user.home`, hãy cấp đường dẫn có chủ đích thay vì tạo quyền ghi cho cả filesystem.

`emptyDir` là vùng tạm theo vòng đời Pod: nó có thể còn sau khi container trong cùng Pod khởi động lại, nhưng không giữ dữ liệu khi Pod bị thay thế. Nếu chọn `medium: Memory`, dữ liệu dùng RAM và phải được tính trong ngân sách bộ nhớ. Bài mẫu dùng medium mặc định. Xem [Volumes của Kubernetes](https://kubernetes.io/docs/concepts/storage/volumes/).

### 6.2. fsGroup không phải lệnh chown toàn bộ container

Volume mount có thể che khuất thư mục đã chuẩn bị trong image. Vì vậy, một lệnh `chown /data` khi build không đảm bảo PVC được mount vào `/data` sẽ có quyền giống như vậy.

Với storage thực tế, cần biết loại volume, khả năng hỗ trợ nhóm của driver và quyền hiện có. `fsGroupChangePolicy` có thể hữu ích với volume được hỗ trợ nhưng không có tác dụng cho mọi loại volume; không thêm nó chỉ với kỳ vọng tối ưu `emptyDir`, ConfigMap hoặc Secret.

Nếu gặp `Permission denied`, kiểm tra UID, GID, nhóm bổ sung, owner và mode của đường dẫn đã mount. Không chọn `chmod -R 777` hoặc init container chạy root như cách sửa mặc định.

### 6.3. ConfigMap và Secret phải đọc được bằng danh tính thật

Secret của ví dụ yêu cầu mode `0440`, kết hợp `fsGroup` để ứng dụng đọc qua quyền nhóm trong môi trường volume được hỗ trợ. Hãy kiểm tra quyền thực tế sau khi mount; đừng chỉ suy từ giá trị khai báo. Khi biểu diễn mode trong JSON, dùng số thập phân tương ứng vì JSON không hỗ trợ cách ghi số bát phân như YAML.

Không in nội dung Secret để kiểm tra quyền. Chỉ kiểm tra khả năng đọc hoặc metadata. Thư mục mount phải có quyền đi xuyên qua, không chỉ bản thân tệp có quyền đọc.

Kubernetes có thể cập nhật dữ liệu Secret đã mount theo cơ chế đồng bộ của nó, nhưng mount dùng `subPath` không nhận cập nhật tự động. Dữ liệu thay đổi trên filesystem cũng không đồng nghĩa bean Spring đang chạy tự được nạp lại. Xem [Secrets của Kubernetes](https://kubernetes.io/docs/concepts/configuration/secret/).

Trong bài này, ConfigMap và Secret được mount cả thư mục. Để kiểm tra một cấu hình mới theo cách đơn giản, có thể cập nhật tài nguyên rồi rollout lại Deployment. Nếu cần cập nhật ứng dụng tại chỗ, thiết kế thêm cơ chế refresh/reload thích hợp với phiên bản Spring Cloud Kubernetes và vòng đời bean của dự án.

## 7. Khi ứng dụng cần gọi Kubernetes API

Non-root vẫn hoạt động với DiscoveryClient và các bộ đọc cấu hình qua API. Điều thay đổi là cần một ServiceAccount có token và RBAC phù hợp, còn UID của Java vẫn giữ nguyên.

Đối với Spring Cloud Kubernetes, quyền cần cấp phụ thuộc starter, chức năng và tài nguyên API mà phiên bản đang dùng truy cập. Bộ đọc ConfigMap không có lý do tự động được cấp quyền đọc Secret; discovery cũng không mặc định cần quyền mọi tài nguyên. Tài liệu [Security Configurations Inside Kubernetes của Spring Cloud Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/security-service-accounts.html) mô tả mối quan hệ giữa client, ServiceAccount và quyền tài nguyên.

Ví dụ sau là **phương án riêng** cho một ứng dụng chỉ đọc/theo dõi ConfigMap qua API trong namespace lab:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: nonroot-api-demo
  namespace: nonroot-lab
automountServiceAccountToken: true
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: nonroot-config-reader
  namespace: nonroot-lab
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: nonroot-config-reader
  namespace: nonroot-lab
subjects:
  - kind: ServiceAccount
    name: nonroot-api-demo
    namespace: nonroot-lab
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: nonroot-config-reader
~~~

Nếu chuyển Deployment sang phương án này, cần thay **cả hai trường** trong `spec.template.spec`:

~~~yaml
serviceAccountName: nonroot-api-demo
automountServiceAccountToken: true
~~~

Thiết lập `false` ở cấp Pod trong manifest ban đầu có ưu tiên hơn thiết lập trên ServiceAccount. Chỉ tạo RoleBinding mà quên đổi cờ tại Pod sẽ không tự cung cấp token cho client.

Cấu hình phía Spring Cloud Kubernetes phải được đổi tương ứng sang phương án đọc API; Role trên không tự kích hoạt một starter hay một nguồn cấu hình. Quyền `list/watch` ở ví dụ áp dụng cho ConfigMap trong namespace và không phải mẫu tối thiểu cho mọi phiên bản hoặc chế độ đọc. Đối chiếu cách client thực hiện request trước khi thu hẹp theo từng tên tài nguyên.

Nếu bật discovery, cần xét riêng quyền cho Service, Endpoint hoặc EndpointSlice và những tài nguyên client thực sự sử dụng. EndpointSlice thuộc API group `discovery.k8s.io`; không chép nó vào nhóm rỗng của ConfigMap. Nếu triển khai Configuration Watcher riêng, cấp quyền cho ServiceAccount của watcher, đồng thời bảo vệ endpoint refresh hoặc luồng restart mà watcher sử dụng.

Chỉ dùng Kubernetes Service DNS và cấu hình qua volume có thể là đủ cho một dịch vụ đơn giản. Quyết định dùng Spring Cloud Kubernetes nên xuất phát từ nhu cầu discovery, load balancing hoặc cập nhật cấu hình cụ thể.

## 8. Kiểm chứng trên cluster

Giả sử đã lưu manifest ở `nonroot-demo.yaml` và đã chuẩn bị image cho cluster:

~~~powershell
kubectl apply -f nonroot-demo.yaml
kubectl rollout status deployment/nonroot-demo -n nonroot-lab --timeout=180s
kubectl get pods -n nonroot-lab -l app=nonroot-demo
kubectl logs -n nonroot-lab deployment/nonroot-demo
~~~

Đọc log để xác nhận web server khởi động và không có lỗi quyền. Sau đó kiểm tra trong container:

~~~powershell
kubectl exec -n nonroot-lab deployment/nonroot-demo -- id
kubectl exec -n nonroot-lab deployment/nonroot-demo -- cat /proc/1/status
kubectl exec -n nonroot-lab deployment/nonroot-demo -- touch /tmp/nonroot-check
kubectl exec -n nonroot-lab deployment/nonroot-demo -- rm /tmp/nonroot-check
kubectl exec -n nonroot-lab deployment/nonroot-demo -- touch /app/should-fail
kubectl exec -n nonroot-lab deployment/nonroot-demo -- ls -ln /etc/app-config/application.yaml /run/secrets/app/demo.password
kubectl exec -n nonroot-lab deployment/nonroot-demo -- sh -c 'test -r /run/secrets/app/demo.password && echo readable'
~~~

Đối chiếu các quan sát:

- `id` hiển thị UID/GID `10001`.
- Các giá trị UID của PID `1` trong `/proc/1/status` không phải `0`; `NoNewPrivs` là `1` và `CapEff` bằng `0` với cấu hình mẫu.
- Tạo/xóa tệp kiểm tra trong `/tmp` thành công.
- Ghi vào `/app` thất bại.
- Secret đọc được nhưng nội dung không bị in ra terminal.

Dockerfile dùng dạng exec cho `ENTRYPOINT` để Java trực tiếp là PID `1`. Với image có launcher hoặc wrapper khác, phải xác định đúng PID của Java trước khi kết luận từ `/proc/1/status`.

Các lệnh `id`, `sh`, `ls` và `cat` phụ thuộc công cụ có trong image. Với distroless, dùng cơ chế chẩn đoán được nền tảng cho phép và bảo đảm quan sát đúng tiến trình/volume của ứng dụng. Không suy UID của Java từ một debug container có danh tính riêng.

Kiểm tra probe qua port-forward trong một terminal:

~~~powershell
kubectl port-forward -n nonroot-lab service/nonroot-demo 8080:80
~~~

Trong terminal khác:

~~~powershell
Invoke-RestMethod http://127.0.0.1:8080/actuator/health/liveness
Invoke-RestMethod http://127.0.0.1:8080/actuator/health/readiness
~~~

Kết quả mong đợi là trạng thái `UP` khi ứng dụng đã sẵn sàng.

Để kiểm tra RBAC của phương án API, người vận hành có quyền impersonate có thể dùng:

~~~powershell
kubectl auth can-i list configmaps -n nonroot-lab --as=system:serviceaccount:nonroot-lab:nonroot-api-demo
kubectl auth can-i get secrets -n nonroot-lab --as=system:serviceaccount:nonroot-lab:nonroot-api-demo
~~~

Với đúng RoleBinding ở mục 7 và không có quyền bổ sung từ binding khác, lệnh đầu trả `yes`, lệnh sau trả `no`. Hai lệnh này kiểm tra phân quyền API, không chứng minh token đã được mount hoặc Java đã đọc được token.

## 9. Chẩn đoán lỗi theo đúng lớp quyền

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `CreateContainerConfigError` liên quan non-root | Image khai báo root hoặc tên user không xác minh được | Đọc sự kiện Pod; khai báo UID số hợp lệ và kiểm tra stage cuối |
| Java không đọc được JAR | Mode tệp hoặc quyền đi qua thư mục | Bổ sung quyền đọc/đi qua cần thiết khi build |
| `Permission denied` tại đường dẫn volume | UID/GID, mode hoặc storage driver không khớp | Kiểm tra metadata thực tế và chính sách volume |
| `Read-only file system` | Ứng dụng đang ghi ngoài vùng được cấp | Chuyển đường dẫn ghi sang volume phù hợp |
| Không tạo được thư mục tạm | `java.io.tmpdir` hoặc quyền `/tmp` sai | Kiểm tra mount và ngân sách dung lượng |
| Kubernetes API trả `403 Forbidden` | Danh tính đã xác thực nhưng thiếu quyền cho request | Xem resource, API group, namespace, verb và RoleBinding |
| Client không có thông tin xác thực hoặc nhận `401` | Token không được cung cấp, không đọc được hoặc không hợp lệ | Kiểm tra cấu hình client, đường dẫn token và cờ automount |
| `ImagePullBackOff` | Image không có trên node hoặc registry không truy cập được | Chuẩn bị image/pull secret; không đổi UID |
| Probe trả `404` hoặc `401/403` | Sai URL, thiếu Actuator hoặc quy tắc bảo mật HTTP | Sửa endpoint và chính sách truy cập probe |
| Admission từ chối Pod | Vi phạm chính sách bảo mật hoặc dải UID | Đọc lý do từ admission và điều chỉnh manifest theo nền tảng |

Để xem nguyên nhân tạo container thất bại, lấy đúng tên Pod từ `kubectl get pods` rồi dùng `kubectl describe pod`. Với container khởi động rồi thoát, xem thêm `kubectl logs --previous` cho đúng Pod/container nếu có lần chạy trước.

Một lỗi `403` không được sửa bằng `USER root`. Một lỗi ghi vào root filesystem chỉ đọc cũng không được giải quyết bằng cấp `cluster-admin`. Mỗi thay đổi quyền phải gắn với thao tác thực sự cần thực hiện.

## 10. Bài thực hành tự kiểm tra

1. Build image và xác minh `Config.User` có UID/GID dạng số.
2. Chạy image với root filesystem chỉ đọc; xác nhận ứng dụng khởi động được và vùng tạm hoạt động.
3. Triển khai manifest Kubernetes, xác nhận UID của Java, quyền đọc Secret và trạng thái probe.
4. Trong bản manifest lab, thử bỏ mount `/tmp` trong khi giữ root filesystem chỉ đọc. Quan sát đường dẫn lỗi của ứng dụng nếu nó cần file tạm; một ứng dụng không ghi tạm có thể vẫn chạy. Khôi phục mount sau thử nghiệm.
5. Cập nhật giá trị `demo.message` trong ConfigMap, thực hiện `kubectl rollout restart deployment/nonroot-demo -n nonroot-lab` và kiểm tra Pod mới vẫn chạy non-root.
6. Giải thích vì sao phương án đọc volume không cần Role đọc ConfigMap cho ServiceAccount của ứng dụng, còn phương án gọi API ở mục 7 cần RBAC.
7. Nêu những tài nguyên và quyền cần đánh giá lại nếu bổ sung DiscoveryClient hoặc Configuration Watcher.

Hoàn thành bài khi bạn có bằng chứng về **danh tính của Java, phạm vi ghi của filesystem, khả năng đọc cấu hình và health probe**. Đồng thời, bạn phải giải thích được lý do cấp hoặc không cấp token Kubernetes API cho ứng dụng. Đây là cơ sở để chọn đúng những tính năng Spring Cloud Kubernetes cần cho triển khai.
