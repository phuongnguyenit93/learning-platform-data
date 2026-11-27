# Listen Address, Advertised Address, and Routability

In service discovery, registering an instance with the right service name is not enough for a consumer to call that instance. The registry must also store an address and port that the consumer can reach. An application might be listening on 0.0.0.0:8080, yet advertise localhost:8080 or a private IP that only exists inside a container. In that case, registration succeeds, but requests from other services fail.

When deploying Spring Cloud with Eureka or Consul, you need to distinguish three concepts: the process listen address, the advertised address in the registry, and the actual network path from the consumer to the instance. These three values may be identical on a development machine, but they often differ when using Docker, Kubernetes, NAT, a reverse proxy, or multiple internal networks.

## 1. Three Types of Addresses to Distinguish

**Listen/bind address** is the interface and port that the application's web server opens to accept connections. Spring Boot typically uses server.address and server.port to configure this part.

**Advertised address** is the hostname or IP, port, and scheme that the application registers in Eureka or Consul. Consumers retrieve this information from the registry to build requests to the instance. This is the routing information advertised to other services.

**Routable address** is an address that a specific consumer can resolve via DNS, open a TCP connection to, and send requests to. An address may be valid from the host's perspective, but invalid from another container's or another subnet's perspective.

For example:

    Application inventory-service
      Listen:      0.0.0.0:8080
      Advertise:   inventory-service:8080
      Consumer:    order-service in the same Docker network
      Route:       inventory-service -> current container IP -> port 8080

If the registry advertises localhost:8080, order-service will call localhost of the order-service container itself. If the registry advertises an old container IP, that address may no longer be valid after the container is recreated.

| Concept | Question to answer | Example |
|---|---|---|
| Listen/bind | On which interface and port does the process accept connections? | 0.0.0.0:8080 |
| Advertise | Which host, port, and scheme will the registry give to the consumer? | inventory-service:8080 |
| Route | Does the consumer have DNS, route, firewall, and permission to access that address? | order-service can call inventory-service:8080 |

An instance can serve requests only when all three layers match the actual network topology.

## 2. Configuring the Listen Address in Spring Boot

By default, the Spring Boot embedded web server listens for HTTP on port 8080. You can change the port with server.port and specify the bind interface with server.address.

For example:

    server:
      address: 0.0.0.0
      port: 8080

0.0.0.0 means listening on all available IPv4 interfaces in the process's network namespace. This is usually the appropriate choice when the application runs in a container and needs to accept connections from other containers.

If set to:

    server:
      address: 127.0.0.1
      port: 8080

the application only accepts loopback connections inside its own network namespace. Another container cannot directly call 127.0.0.1:8080 of this container.

Distinguish the bind address from the advertised address. Setting server.address=0.0.0.0 does not mean the registry should advertise 0.0.0.0. That is a wildcard address for binding, not a destination address for consumers to connect to.

The listen port can differ from the advertised port. For example, the application listens on 8080 while a reverse proxy accepts external connections on 443. In that case, the registry may need to advertise the proxy's hostname and port 443, while server.address and server.port remain 0.0.0.0:8080.

## 3. Why Does Registration Succeed but Consumers Cannot Call It?

The registry only stores the instance information provided by the client. It does not automatically create network routes between containers, virtual machines, or subnets.

Some common errors:

- **Advertising localhost:** the consumer calls its own loopback instead of the target instance.
- **Advertising a container IP:** the IP can change when the container is recreated or scaled.
- **Advertising a private IP on the wrong network:** the IP is valid, but a consumer in another subnet has no route to that address.
- **Wrong port:** the application listens on container port 8080, but the registry advertises the host port or an incorrect proxy port.
- **Wrong hostname:** DNS only resolves within one network or one datacenter, while the consumer is outside that scope.
- **Wrong scheme:** the registry advertises http while the proxy only accepts https, or vice versa.
- **Firewall/network policy:** DNS and TCP may work in one direction but be blocked in the direction from the consumer to the service.
- **Wrong health check address:** the Consul Agent cannot reach the check endpoint even though consumers can call the business endpoint.

Therefore, seeing a service appear on the Eureka Dashboard or Consul Catalog only proves that the registration record was saved. You must test connectivity from the consumer's own environment to verify the routing path.

## 4. Configuring the Advertised Address with Consul

Spring Cloud Consul automatically determines the instance's hostname and IP based on the environment. You can override this information with the following properties:

- spring.cloud.consul.discovery.hostname: advertised hostname.
- spring.cloud.consul.discovery.ip-address: advertised IP.
- spring.cloud.consul.discovery.prefer-ip-address: prefer using IP instead of hostname.
- spring.cloud.consul.discovery.port: advertised port; defaults to the listen port.
- spring.cloud.consul.discovery.scheme: http or https scheme.

Example when services run on the same Docker Compose network:

    server:
      address: 0.0.0.0
      port: 8080

    spring:
      application:
        name: inventory-service
      cloud:
        consul:
          host: consul
          port: 8500
          discovery:
            register: true
            hostname: inventory-service
            prefer-ip-address: false
            port: 8080
            scheme: http

In the example:

- server.address and server.port control the web server of inventory-service.
- spring.cloud.consul.host and port are the Consul Agent address that the application calls to register.
- discovery.hostname and discovery.port are the service address advertised to consumers.
- The hostname inventory-service only resolves from containers located on a network with the corresponding DNS record.

Do not confuse spring.cloud.consul.host with spring.cloud.consul.discovery.hostname. The first property specifies where the application calls the Consul Agent API; the second is the instance address that Consul registers for consumers to use.

If you want to advertise an IP instead of a hostname:

    spring:
      cloud:
        consul:
          discovery:
            ip-address: 10.20.0.15
            prefer-ip-address: true

The IP must be an address to which all consumers that need to call it can route. Do not choose a loopback IP, an IP of an unreachable management interface, or an internal container IP that is only meaningful on a single node.

## 5. Configuring the Advertised Address with Eureka

The Eureka Client sends instance information such as hostname, IP, port, and instance ID to the Eureka Server. Commonly used properties include:

- eureka.instance.hostname: advertised hostname.
- eureka.instance.ip-address: instance IP.
- eureka.instance.prefer-ip-address: prefer advertising IP instead of hostname.
- eureka.instance.instance-id: unique identifier of the instance within the service.
- eureka.instance.non-secure-port and secure-port: advertised ports for HTTP and HTTPS.
- eureka.instance.non-secure-port-enabled and secure-port-enabled: enable/disable the corresponding endpoint type.

Example using an internal hostname resolvable from consumers:

    server:
      address: 0.0.0.0
      port: 8080

    spring:
      application:
        name: inventory-service

    eureka:
      instance:
        hostname: inventory-service.internal
        prefer-ip-address: false
        non-secure-port: 8080
        non-secure-port-enabled: true
        instance-id: ${spring.application.name}:${HOSTNAME:node-01}:${server.port}

If consumers cannot resolve the hostname but have a route to the instance IP, you can use:

    eureka:
      instance:
        ip-address: 10.20.0.15
        prefer-ip-address: true

Setting prefer-ip-address=true instructs Eureka to advertise the IP instead of the hostname. Verify that the IP the application picks actually belongs to the interface used for inter-service communication. Machines with multiple NICs, VPNs, or container interfaces can cause the auto-detected address not to be an address reachable by consumers.

If you run multiple instances of the same service on one machine, make sure the instance ID is not duplicated. An identifier typically combines the service name with the hostname or container ID and port. If two instances register the same ID, information can be overwritten or cause confusion in the registry.

## 6. Distinguishing Advertised Address and Port When Using a Reverse Proxy

A common pattern is that the application runs in a private network, while consumers access it through a reverse proxy or load balancer:

    Consumer
       |
       | https://inventory.api.internal:443
       v
    Reverse proxy / Load balancer
       |
       | http://inventory-service:8080
       v
    Spring Boot inventory-service

In this model:

- Spring Boot listens on 0.0.0.0:8080.
- The reverse proxy receives HTTPS at inventory.api.internal:443.
- The proxy forwards requests into the application over HTTP port 8080.
- If consumers will call through the proxy, the registry must advertise inventory.api.internal and port 443 with the HTTPS scheme.
- If consumers are in the same private network and call the container directly, the registry can advertise inventory-service:8080.

You cannot use a single advertised address for every consumer group if the groups have different network paths. You may need internal DNS, separate registries per environment, a service gateway, or a VIP address reachable from all relevant consumers.

With Eureka, configuring an HTTPS endpoint can use:

    eureka:
      instance:
        hostname: inventory.api.internal
        non-secure-port-enabled: false
        secure-port-enabled: true
        secure-port: 443
        secure-health-check-url: https://inventory.api.internal/actuator/health
        status-page-url: https://inventory.api.internal/actuator/info
        home-page-url: https://inventory.api.internal/

With Consul, configuring a service advertised through a proxy can use:

    spring:
      cloud:
        consul:
          discovery:
            hostname: inventory.api.internal
            prefer-ip-address: false
            port: 443
            scheme: https
            health-check-url: http://inventory-service:8080/actuator/health

The Consul example above advertises HTTPS port 443 for consumers, but the health check goes directly to the internal HTTP endpoint on port 8080. The Consul Agent must be in a network that can reach inventory-service:8080. Only use a separate health-check-url when the check address truly differs from the advertised address; ensure the internal endpoint is also protected by an appropriate network policy.

If TLS is terminated at the proxy, the application may need to be configured to handle forwarded headers so it generates absolute URLs with the correct external scheme and host. This does not automatically change the registered address; the hostname, port, and scheme settings in the registry still need to be configured appropriately.

## 7. Docker Compose: Host Port and Container Port

Docker Compose creates a default network for services in the same project. Containers can find each other by service name via internal DNS. Container IPs can change after recreation, while service names stay stable.

For example:

    services:
      inventory-service:
        image: example/inventory-service
        environment:
          SERVER_ADDRESS: 0.0.0.0
          SERVER_PORT: 8080
        ports:
          - "18080:8080"
        networks:
          - backend

      order-service:
        image: example/order-service
        environment:
          SPRING_CLOUD_CONSUL_HOST: consul
          SPRING_CLOUD_CONSUL_PORT: 8500
        networks:
          - backend

      consul:
        image: hashicorp/consul:latest
        command: agent -dev -client=0.0.0.0
        ports:
          - "8500:8500"
        networks:
          - backend

    networks:
      backend:

In the example, Consul runs in dev mode for local experimentation; do not use this mode for production. In a real environment, deploy Consul Agent with an appropriate cluster and security configuration.

There are two ways to access inventory-service:

| Caller location | Address | Port |
|---|---|---:|
| Container order-service in backend network | inventory-service | 8080 |
| Host machine | localhost | 18080 |

If the Consul Agent runs in the consul container on the same network, it can also access inventory-service:8080 to perform HTTP health checks. Therefore, in this model Consul should store the advertised address inventory-service:8080, not localhost:18080.

Host port 18080 is only needed when a process outside the Docker network accesses it from the host machine. Container-to-container communication uses container port 8080. Do not register host port 18080 if consumers inside the network need to call internal port 8080.

If the Consul Agent runs directly on the host instead of in a container, the health check address and registered address must be re-evaluated according to the network path from the host to the container. You can use the host address and published port, or place the agent on the same network as the service to use the service DNS name and container port.

## 8. Kubernetes and Pod/Service Addresses

In Kubernetes, a Pod IP is usually only meaningful within the cluster network and can change when the Pod is recreated. A Kubernetes Service provides a stable DNS address for a group of Pods.

For example:

    Spring Boot container:
      listen: 0.0.0.0:8080

    Kubernetes Service:
      service port: 80
      targetPort: 8080

    Consumer in the same cluster:
      http://inventory-service:80

If the application registers the Pod IP directly into Eureka or Consul, every consumer must have a route to the Pod CIDR and network policies must allow the connection. If you want consumers to call through a Kubernetes Service, the advertised address should be the Service DNS and service port. Ensure the registry's health check can also reach the configured address.

Do not assume that Pod IP, Node IP, Service ClusterIP, and LoadBalancer IP are interchangeable. They belong to different network scopes:

| Address | Typical usage scope |
|---|---|
| Pod IP | Direct communication to a Pod inside the cluster network |
| ClusterIP / Service DNS | Communication to a Kubernetes Service from inside the cluster |
| Node IP + NodePort | Access via a node and published port |
| LoadBalancer IP/hostname | Access via a load balancer outside the cluster |

Choose the address type based on where the consumer is located, not based on whichever address is easiest to obtain from the application.

## 9. Management Port and Health Check

An application can run management endpoints on a separate port:

    server:
      address: 0.0.0.0
      port: 8080

    management:
      server:
        port: 8081

When the management server uses a different port from the application server, Spring Cloud Consul registers a separate management service. Consul discovery provides management-port, management-suffix, and management-tags properties to customize that registration.

Distinguish between:

- Business port is the address consumers use to call APIs.
- Management port is usually dedicated to health, metrics, and operations.
- Health check port is where the Consul Agent calls the check endpoint.

Do not advertise the management port as the business port if consumers should not access it. Also do not expose the management port to a public network just so the Consul Agent can check it. Use an internal network, ACLs, or a separate health-check-url to restrict access paths.

With Eureka, health-check-url, secure-health-check-url, status-page-url, and home-page-url can be configured separately when endpoints sit behind a proxy or differ from the instance address. These URLs must reflect the actual access path of the component that will use them.

## 10. DNS, NAT, Firewall, and Routing

An advertised hostname is only useful when the consumer can resolve it to the appropriate IP address. In multi-network environments, the same hostname can resolve differently depending on the DNS view or search domain.

When testing, verify from the exact consumer environment:

1. Does DNS return the expected IP?
2. Does that IP belong to a network that the consumer has a route to?
3. Do firewalls, security groups, and network policies allow TCP to the advertised port?
4. Is the service actually listening on that interface and that port?
5. If NAT or port mapping is present, is the port used by the consumer forwarded to the right container/server port?
6. If HTTPS is used, does the hostname match the certificate and is the trust chain valid?
7. If going through a proxy, does the proxy route to the upstream and forward the correct path, method, and headers?

NAT can make the internal address differ from the external address. If consumers are outside NAT, registering an internal private address is usually not enough. You must advertise an external hostname/IP and port that consumers can reach, or use an overlay network/VPN so parties have direct routes.

Do not use ping as the sole proof. ICMP may be blocked while TCP works, or ping may succeed while the application port is still closed. Test TCP and HTTP/HTTPS to the exact port.

## 11. Verifying the Address from the Consumer Side

A practical diagnostic workflow should start at the registry and end at a real request.

**Step 1: Check the address the registry is advertising**

With Consul, query the service catalog:

    curl http://consul:8500/v1/catalog/service/inventory-service

Inspect ServiceAddress, ServicePort, ServiceName, Node, and datacenter. If ServiceAddress is empty, Consul may use the node address according to catalog rules; verify the resulting address that consumers receive.

With Eureka, open the Dashboard or query the registry to view the hostname, IP, port, status, and instance ID registered by the client.

**Step 2: Check DNS from the consumer**

    nslookup inventory-service

The command must be run inside the consumer's container or machine. Running it on the host can yield different results than inside the container.

**Step 3: Check HTTP from the consumer**

    curl -v http://inventory-service:8080/actuator/health

If the service is advertised via an HTTPS proxy:

    curl -v https://inventory.api.internal/actuator/health

If DNS resolves correctly but the connection times out, check routes, firewalls, and security groups. If TCP connects but returns 404, check the context path or reverse proxy routing. If it returns 401/403, check authentication and access permissions. If TLS fails, check the certificate hostname, CA, and SNI.

**Step 4: Compare with the listen address**

On the machine or container running the service, confirm that the process is actually listening on the configured port and interface. On Linux you can use ss -lntp; inside a container you can use an equivalent tool available in the image or inspect Spring Boot startup logs.

**Step 5: Call via service discovery**

Once the direct address works, test DiscoveryClient or Spring Cloud LoadBalancer to confirm the consumer receives the right URI and requests are routed to the intended instance.

## 12. Common Errors Table

| Symptom | Possible cause | Resolution |
|---|---|---|
| Service is in registry but requests time out | Advertised IP/hostname has no route from consumer | Advertise an address reachable by consumers; check firewall and subnet |
| Consumer calls localhost and hits itself | Registry contains localhost | Set the instance's hostname/IP instead of loopback |
| Other containers cannot call the application | server.address binds 127.0.0.1 | Bind to 0.0.0.0 or the appropriate interface |
| Docker host can call it but containers cannot | Using host port or localhost in the wrong scope | Use service DNS name and container port |
| Consul health check is critical but API works from host | Consul Agent is in another network or health check uses wrong port/path | Check from the agent's network and configure health-check-url/path |
| Requests go to the wrong port behind reverse proxy | Registry advertises internal port instead of proxy port, or vice versa | Choose one consistent call path and configure the advertised port |
| HTTPS returns certificate error | Advertised hostname does not match SAN or CA is untrusted | Use DNS matching the certificate and configure trust |
| Eureka displays an unresolvable hostname | Java auto-selects a hostname unsuitable for the network | Set eureka.instance.hostname or prefer-ip-address |
| Consul advertises the wrong interface | Auto-detect picks the wrong NIC/VPN/container interface | Set hostname or ip-address and prefer-ip-address explicitly |
| Health endpoint works but consumers still cannot call it | Health check only proves the agent can reach the check endpoint | Check the route separately from consumer to application endpoint |

## 13. Principles for Choosing an Advertised Address

When deciding the registration address for a service, answer in order:

1. Which consumers need to call this instance?
2. Are those consumers in the same Docker network, same Kubernetes cluster, same VPC, or across an external network?
3. Is there a stable hostname resolvable from all consumers?
4. Should consumers call the instance directly or go through a proxy/load balancer?
5. Which port and scheme are actually open on that path?
6. Where does the health checker run, and is a separate URL needed?
7. Will the address remain valid after restart, reschedule, or scaling?

If all consumers are on the same overlay network, a service DNS name is usually more stable and easier to manage than container IPs. If consumers span multiple networks, use DNS/VIP or a gateway reachable across those networks. If a service has both internal and external consumers, two different endpoints or two different registrations may be needed instead of a single advertised address.

Do not advertise an IP just because the registry allows storing IPs. The address must be tested from where consumers run and must have a lifecycle compatible with how the instance is deployed.

## 14. Conclusion

The listen address describes where the Spring Boot process opens its socket; the advertised address describes the host, port, and scheme that Eureka or Consul returns to consumers; routability determines whether consumers can actually connect to that address. server.address and server.port control bind/listen, while spring.cloud.consul.discovery.hostname/ip-address/port or eureka.instance.hostname/ip-address/port control registration information.

In Docker and Kubernetes, prefer stable hostnames or service DNS within the right network scope, and use the appropriate container port or Service port. When NAT or a reverse proxy is present, advertise the address that consumers actually access and configure health checks along a path the agent can use. Finally, verify DNS, TCP, and HTTP/TLS from the consumer itself; a successful registration does not prove that the route works.

## References

- [Spring Boot — Embedded Web Servers](https://docs.spring.io/spring-boot/how-to/webserver.html)
- [Spring Cloud Consul — Configuring the Service Hostname and IP Address](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Spring Cloud Consul — Common Application Properties](https://docs.spring.io/spring-cloud-consul/reference/appendix.html)
- [Spring Cloud Netflix — Eureka Instance Configuration](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html)
- [Spring Cloud Netflix — Registering a Secure Application and Eureka Instance URLs](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Docker Compose — Networking](https://docs.docker.com/compose/how-tos/networking/)
