# Configuring Scrape Targets, Paths, Ports, and Credentials

When Prometheus scrapes metrics from Spring Boot, it needs to call the right **URL from the Prometheus process's perspective**. An endpoint can return data when called on the application host yet still report errors in Prometheus if the two sides use different ports, paths, or credentials.

## 1. Separate target address from path

A static scrape job builds the URL from three components:

~~~text
Scrape URL = scheme + "://" + target + metrics_path
~~~

- `static_configs[].targets` lists `host:port` addresses, such as `shop.ops.example.com:9443`. The DNS name and port must be reachable from the environment where Prometheus runs.
- `metrics_path` is the absolute path component, such as `/actuator/prometheus`. Prometheus defaults to `/metrics` if this field is omitted.
- `scheme` is `http` or `https`. Default is `http`. Choose based on the protocol the target host accepts on the declared port.

If Prometheus runs in a container, `localhost` points to that container itself. If the job scrapes individual instances, declare each instance's address or use a service discovery mechanism that returns individual targets. A load-balanced address can route each scrape to a different instance and mix measurements across processes.

## 2. Determine Actuator port and path

The example uses Spring Boot 3.3 with Spring MVC, Actuator, and the Prometheus registry already in the application. Put the following configuration in `application.properties`:

~~~properties
server.port=8080
server.servlet.context-path=/shop
management.server.port=9091
management.server.address=127.0.0.1
management.server.base-path=/ops
management.endpoints.web.base-path=/manage
management.endpoints.web.path-mapping.prometheus=metrics
management.endpoints.web.exposure.include=health,prometheus
~~~

The application listens on port 8080. The management server listens on port 9091, on loopback only. Because the two ports differ, the endpoint's internal path is composed from `/ops` (management server prefix), `/manage` (endpoints prefix), and `/metrics` (mapped path name). The ID to expose over HTTP remains `prometheus`. The internal management URL is `http://127.0.0.1:9091/ops/manage/metrics`.

| Deployment setup | How to determine the path |
| --- | --- |
| Shared application port | Combine `server.servlet.context-path`, `management.endpoints.web.base-path`, and the endpoint's path segment. With `/shop` and default paths, the URL ends with `/shop/actuator/prometheus`. |
| Separate management port | Combine `management.server.base-path`, `management.endpoints.web.base-path`, and the endpoint's path segment. With the configuration above, the URL ends with `/ops/manage/metrics`. |
| Behind a reverse proxy | Prometheus calls the address and path exposed by the proxy. If the proxy rewrites the path, use the Prometheus-side path for `metrics_path`. |

In the example, the proxy runs directly on the **same host** as the application. The proxy accepts HTTPS at `shop.ops.example.com:9443`, requires HTTP Basic with the monitoring account `prometheus-scraper`, and forwards the exact path `/ops/manage/metrics` to `127.0.0.1:9091`. This is an assumption about the example's proxy configuration. When using Spring Security for authentication at the application, access rules must grant permission to call the endpoint to the monitoring account. With a custom `SecurityFilterChain`, the application is responsible for configuring this permission.

## 3. Configure the job and credentials

Add the following job to `scrape_configs` in `prometheus.yml`:

~~~yaml
scrape_configs:
  - job_name: 'shop-actuator'
    scheme: 'https'
    metrics_path: '/ops/manage/metrics'
    scrape_interval: 30s
    scrape_timeout: 5s
    follow_redirects: false
    static_configs:
      - targets: ['shop.ops.example.com:9443']
    basic_auth:
      username: 'prometheus-scraper'
      password_file: '/run/secrets/shop_actuator_password'
    tls_config:
      ca_file: '/etc/prometheus/certs/shop-ops-ca.pem'
~~~

The job calls `https://shop.ops.example.com:9443/ops/manage/metrics` every 30 seconds and waits up to 5 seconds. Choose a timeout appropriate for the endpoint and keep `scrape_timeout` no greater than `scrape_interval`. The example disables following redirects so errors pointing to a login page show up clearly right at the scrape step.

- **HTTP Basic** sends the username and password in the `Authorization` header. Use HTTPS over the link to the proxy and provide `password_file` for the Prometheus process to read. The file holds the monitoring account's password and stays outside source code.
- **TLS** uses `ca_file` when the proxy uses a certificate issued by an internal CA. The file path is resolved within the Prometheus environment, such as inside the container if the process runs in a container. The hostname in `targets` must match the certificate presented by the proxy.
- **Bearer token** applies when the endpoint or proxy requires a token. In that case, replace the entire `basic_auth` block with the block below and provide the token file to the Prometheus process:

~~~yaml
authorization:
  type: 'Bearer'
  credentials_file: '/run/secrets/shop_actuator_token'
~~~

Choose one authentication mechanism per job. If the system requires Prometheus to obtain a token via the OAuth 2.0 client credentials flow, use the corresponding `oauth2` configuration. The `basic_auth` and `authorization` fields above are **Prometheus-side request** configurations. Accepting the request is enforced by the proxy or the application.

## 4. Verify in order from URL to metric samples

1. Validate the configuration before reloading Prometheus:

   ~~~bash
   promtool check config /etc/prometheus/prometheus.yml
   ~~~

2. From an environment sharing the same network path as Prometheus, test the exact URL, CA, and account. `curl` will prompt for the password because the command only provides the username:

   ~~~bash
   curl -sS -i --max-time 5 --cacert /etc/prometheus/certs/shop-ops-ca.pem --user prometheus-scraper https://shop.ops.example.com:9443/ops/manage/metrics
   ~~~

   The result should have HTTP 200 and a response body containing samples in Prometheus format, such as `# TYPE` lines and JVM metrics. If you receive HTML, check whether the proxy is returning a login page or the application is misrouting.

3. After reloading the configuration, inspect the job's URL and latest error on the Prometheus Targets page. After the first scrape, query `up{job="shop-actuator"}`. A value of 1 confirms Prometheus scraped successfully from that target. A value of 0 indicates the scrape failed. If there is no `up` series for the job yet, check configuration reloading, the target list, and the first scrape time.

| Symptom | Next check |
| --- | --- |
| `connection refused` or timeout | Check DNS, exposed port, listening address, and connectivity from the Prometheus network. |
| TLS verification error | Check `scheme`, trusted CA, certificate expiration, and the hostname in the certificate. |
| HTTP 401 | Check the authentication mechanism expected by the target, username or token, and read permissions on the credential file. |
| HTTP 403 | Check permissions of the monitoring account and network or proxy policies applied to the path. |
| HTTP 404 | Cross-check the actual port and path, proxy rewrite rules, and HTTP exposure configuration for the `prometheus` ID. |

### References

- [Spring Boot 3.3 – HTTP management paths and ports](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html)
- [Spring Boot 3.3 – Exposing and securing Actuator endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
- [Prometheus – Scrape, HTTP, and TLS configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)